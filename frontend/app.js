'use strict';

const $ = (id) => document.getElementById(id);
const ROLES = {consolidator: '#e8a25c', transit: '#8a8a8a', distributor: '#5c8dff',
  terminal: '#c2c2c2', coordinator: '#6b62f2', peripheral: '#858585'};
const fmt = new Intl.NumberFormat('ru-RU');
const money = (v) => `${fmt.format(Number(v || 0))} ₸`;
const percent = (v) => `${(Number(v || 0) * 100).toFixed(1)}%`;
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const badge = (role) => `<span class="role-badge" style="background:${ROLES[role] || '#888'}22;color:${ROLES[role] || '#aaa'}">${esc(role || 'без оценки')}</span>`;
const state = {token: sessionStorage.getItem('moneygraph-token'), register: false, generation: 0,
  summary: null, clusters: [], graph: null, focus: null, cluster: null, graphRequest: 0,
  queue: {skip: 0, limit: 50, sort: 'rank', direction: 'asc'}, queueRequest: 0, searchRequest: 0};

function message(text, error = false) {
  $('app-message').textContent = text;
  $('app-message').classList.toggle('error', error);
  $('app-message').hidden = !text;
}

function showAuth(text = '') {
  state.generation++;
  state.token = null;
  sessionStorage.removeItem('moneygraph-token');
  state.summary = null; state.clusters = []; state.graph = null; state.focus = null; state.cluster = null;
  state.graphRequest++; state.queueRequest++; state.searchRequest++;
  $('workspace').hidden = true; $('auth').hidden = false;
  document.querySelector('nav').hidden = true;
  document.querySelector('.search-wrap').hidden = true;
  document.querySelector('.account').hidden = true;
  $('user-email').textContent = ''; $('password').value = '';
  $('auth-error').textContent = text;
  $('gidsearch').value = ''; $('searchdd').classList.remove('show');
  $('ov-top').replaceChildren(); $('ov-roles').replaceChildren(); $('pq-body').replaceChildren();
  $('cl-grid').replaceChildren(); $('netsvg').replaceChildren(); $('nodepanel').replaceChildren();
  $('connection-status').textContent = 'Войдите или создайте аккаунт для работы с данными';
  message('');
}

async function api(path, options = {}) {
  const token = state.token;
  const headers = new Headers(options.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  let response;
  try {
    response = await fetch(path, {...options, headers, signal: AbortSignal.timeout(120000)});
  } catch (error) {
    throw new Error(error.name === 'TimeoutError' ? 'Сервер не ответил вовремя. Обновите данные, чтобы проверить результат.' : 'Нет связи с сервером. Проверьте подключение и повторите запрос.');
  }
  if (!response.ok) {
    let data = {};
    try { data = await response.json(); } catch { /* Non-JSON proxy response. */ }
    const details = Array.isArray(data.detail) ? data.detail.map((e) => `${e.loc?.slice(1).join('.')}: ${e.msg}`).join('; ') : data.detail;
    const known = {401: 'Неверный email или пароль.', 409: 'Запись уже существует.',
      429: `Слишком много попыток. Повторите через ${response.headers.get('Retry-After') || 60} сек.`,
      503: 'Серверная авторизация не настроена. Проверьте JWT_SECRET_KEY.', 500: 'Ошибка сервера. Проверьте доступность базы данных.'};
    if (response.status === 401 && token && token === state.token && !path.startsWith('/auth/')) {
      showAuth('Сессия истекла. Войдите заново.');
    }
    throw new Error(known[response.status] && (response.status !== 409) ? known[response.status] : details || known[response.status] || `Ошибка HTTP ${response.status}`);
  }
  return options.blob ? response.blob() : response.json();
}

function action(button, task) {
  button.addEventListener('click', () => busy(button, task));
}

async function busy(button, task) {
  const generation = state.generation;
  button.disabled = true;
  try { await task(); } catch (error) { if (generation === state.generation) message(error.message, true); }
  finally { button.disabled = false; updateActions(); }
}

function updateActions() {
  $('analyze').disabled = !state.summary?.nodes || !!state.mutating;
  $('download').disabled = !state.summary?.analysis_ready || !!state.mutating;
  $('upload').hidden = !!state.summary?.nodes;
  $('upload').disabled = !!state.mutating;
  $('refresh').disabled = !!state.mutating;
}

function navigate(view) {
  document.querySelectorAll('nav [data-v]').forEach((b) => b.classList.toggle('active', b.dataset.v === view));
  document.querySelectorAll('.view').forEach((v) => v.classList.toggle('active', v.id === view));
}

async function authenticated() {
  const generation = state.generation;
  const user = await api('/auth/me');
  if (generation !== state.generation) return;
  $('auth').hidden = true; $('workspace').hidden = false;
  document.querySelector('nav').hidden = false;
  document.querySelector('.search-wrap').hidden = false;
  document.querySelector('.account').hidden = false;
  $('user-email').textContent = user.email;
  $('password').value = ''; $('auth-error').textContent = '';
  $('queue-search').value = ''; $('queue-role').value = ''; state.queue.skip = 0;
  navigate('overview');
  await refresh();
}

async function allClusters() {
  const result = [];
  for (let skip = 0; ; skip += 100) {
    const rows = await api(`/clusters/?skip=${skip}&limit=100`);
    result.push(...rows);
    if (rows.length < 100) return result;
  }
}

async function refresh() {
  const generation = state.generation;
  $('connection-status').textContent = 'Загрузка данных…';
  const [summary, top, clusters] = await Promise.all([api('/dataset'), api('/ranking/search?limit=6'), allClusters()]);
  if (generation !== state.generation) return;
  state.summary = summary; state.clusters = clusters;
  for (const key of ['nodes', 'edges', 'seeds', 'clusters']) $(`kpi-${key}`).textContent = fmt.format(summary[key]);
  $('overview-sub').textContent = `${fmt.format(summary.transactions)} транзакций · ${money(summary.total_kzt)}${summary.date_min ? ` · ${summary.date_min} — ${summary.date_max}` : ''}`;
  $('connection-status').textContent = summary.nodes ? `Данные из базы · ${fmt.format(summary.nodes)} узлов · ${summary.analysis_ready ? 'анализ готов' : 'нужен пересчёт'}` : 'База подключена · загрузите датасет';
  $('empty-dataset').hidden = !!summary.nodes;
  $('depth-warning').textContent = `${fmt.format(summary.truncated_nodes)} узлов 4-го колена без исходящих переводов. Это граница выгрузки, а не подтверждённые конечные получатели.`;
  $('analysis-meta').textContent = `${summary.method}${summary.analyzed_at ? ` Последний расчёт: ${new Date(summary.analyzed_at).toLocaleString('ru-RU')}.` : ''}`;
  $('ov-top').innerHTML = top.items.map((n) => `<div class="prow"><span class="rank">${n.rank}</span><button class="btn link gid" data-gid="${esc(n.gid)}">${esc(n.gid)}</button>${badge(n.role)}<span class="bar"><i style="width:${n.priority_score * 100}%"></i></span><span class="pct">${percent(n.priority_score)}</span></div>`).join('') || '<div class="empty">Очередь появится после анализа данных.</div>';
  $('ov-roles').innerHTML = Object.entries(ROLES).map(([role, color]) => {
    const count = summary.role_counts[role] || 0;
    return `<div class="rd-row"><span>${role}</span><span class="rd-bar"><i style="width:${summary.nodes ? count / summary.nodes * 100 : 0}%;background:${color}"></i></span><span>${fmt.format(count)}</span></div>`;
  }).join('');
  $('cl-grid').innerHTML = clusters.map((c) => `<button class="cl-card" data-cluster="${c.cluster_id}"><div class="id">CLUSTER #${c.cluster_id}</div><div class="vol">${money(c.sum_kzt_internal)}</div><div class="meta"><span>${fmt.format(c.n_nodes)} узлов</span><span>${c.n_seed} seed</span></div><div class="hyp">${esc(c.hypothesis)}</div></button>`).join('') || '<div class="empty">Нет рассчитанных кластеров.</div>';
  const clusterFilter = $('queue-cluster').value;
  $('queue-cluster').innerHTML = '<option value="">Все кластеры</option>' + clusters.map((c) => `<option value="${c.cluster_id}">Кластер #${c.cluster_id}</option>`).join('');
  $('queue-cluster').value = clusters.some((c) => String(c.cluster_id) === clusterFilter) ? clusterFilter : '';
  updateActions();
  await loadQueue();
  if (generation !== state.generation) return;
  await loadGraph();
}

async function loadQueue() {
  const request = ++state.queueRequest;
  const params = new URLSearchParams({...state.queue, q: $('queue-search').value.trim()});
  if ($('queue-role').value) params.set('role', $('queue-role').value);
  if ($('queue-cluster').value) params.set('cluster_id', $('queue-cluster').value);
  const data = await api(`/ranking/search?${params}`);
  if (request !== state.queueRequest || !state.token) return;
  if (data.total && state.queue.skip >= data.total) { state.queue.skip = 0; return loadQueue(); }
  $('pq-body').innerHTML = data.items.map((n) => `<tr class="trow"><td>${n.rank}</td><td><button class="btn link gid" data-gid="${esc(n.gid)}">${esc(n.gid)}</button></td><td>${badge(n.role)}</td><td>${percent(n.priority_score)}</td><td>${n.cluster_id == null ? '—' : '#' + n.cluster_id}</td><td class="evid">${esc(n.evidence)}</td></tr>`).join('') || '<tr><td colspan="6" class="empty">По выбранным фильтрам узлы не найдены.</td></tr>';
  $('queue-page').textContent = data.total ? `${data.skip + 1}–${Math.min(data.skip + data.limit, data.total)} из ${fmt.format(data.total)}` : '0 узлов';
  $('queue-prev').disabled = state.queue.skip === 0;
  $('queue-next').disabled = state.queue.skip + state.queue.limit >= data.total;
}

async function loadGraph() {
  const request = ++state.graphRequest;
  const params = new URLSearchParams({limit: 250, hops: $('graph-hops').value});
  if (state.focus) params.set('gid', state.focus);
  if (state.cluster != null) params.set('cluster_id', state.cluster);
  $('graph-status').textContent = 'Загрузка связей…';
  const data = await api(`/graph?${params}`);
  if (request !== state.graphRequest || !state.token) return;
  state.graph = data;
  $('cluster-queue').hidden = state.cluster == null;
  drawGraph();
}

function drawGraph() {
  if (!state.graph) return;
  const active = new Set([...document.querySelectorAll('#role-filters input:checked')].map((i) => i.value));
  const visible = state.graph.nodes.filter((n) => !n.role || active.has(n.role));
  const positions = new Map();
  for (let depth = 0; depth <= 4; depth++) {
    const layer = visible.filter((n) => n.depth === depth);
    layer.forEach((n, i) => positions.set(n.gid, {x: 75 + depth * 155 + (layer.length > 22 ? (i % 3 - 1) * 25 : 0), y: 50 + (i + 1) * 460 / (layer.length + 1)}));
  }
  let html = '<defs><marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 Z" fill="#65748a"/></marker></defs>';
  for (let depth = 0; depth <= 4; depth++) html += `<text x="${75 + depth * 155}" y="25" text-anchor="middle" fill="#8a8a8a" font-size="12">${depth === 0 ? 'Seed · 0' : 'Колено ' + depth}</text>`;
  for (const edge of state.graph.edges) {
    const a = positions.get(edge.src), b = positions.get(edge.dst);
    if (!a || !b) continue;
    const target = visible.find((n) => n.gid === edge.dst);
    const dx = b.x - a.x, dy = b.y - a.y, length = Math.hypot(dx, dy) || 1;
    const inset = 5 + target.priority_score * 7;
    const path = edge.src === edge.dst ? `M${a.x} ${a.y - 7} C${a.x + 32} ${a.y - 36},${a.x + 32} ${a.y + 30},${a.x + 5} ${a.y + 7}` : `M${a.x} ${a.y} L${b.x - dx / length * inset} ${b.y - dy / length * inset}`;
    html += `<path d="${path}" fill="none" stroke="#3a4658" stroke-width="1.2" marker-end="url(#arrow)"><title>${esc(edge.src)} → ${esc(edge.dst)} · ${esc(money(edge.sum_kzt))} · ${edge.n_tx} переводов</title></path>`;
  }
  for (const n of visible) {
    const p = positions.get(n.gid);
    html += `<circle cx="${p.x}" cy="${p.y}" r="${4 + n.priority_score * 7}" fill="${ROLES[n.role] || '#aaa'}" stroke="${n.gid === state.focus ? '#fff' : 'transparent'}" stroke-width="2" data-gid="${esc(n.gid)}" tabindex="0" role="button" aria-label="Узел ${esc(n.gid)}"><title>${esc(n.gid)} · ${esc(n.role || 'без оценки')} · ${percent(n.priority_score)}</title></circle>`;
  }
  if (!visible.length) html += '<text x="390" y="280" text-anchor="middle" fill="#c2c2c2">Нет узлов для отображения</text>';
  $('netsvg').innerHTML = html;
  $('graph-status').textContent = `${state.focus ? 'Окружение ' + state.focus + ' · ' : state.cluster != null ? 'Кластер #' + state.cluster + ' · ' : ''}${visible.length} показано из ${fmt.format(state.graph.total_nodes)}${state.graph.truncated ? ' · ограничено до 250 узлов по приоритету' : ''}${visible.length < state.graph.shown_nodes ? ' · применён фильтр ролей' : ''}`;
}

async function openNode(gid) {
  const generation = state.generation;
  state.focus = gid; state.cluster = null;
  navigate('network');
  document.querySelectorAll('#role-filters input').forEach((i) => { i.checked = true; });
  $('nodepanel').textContent = 'Загрузка узла…';
  const n = await api(`/graph/nodes/${encodeURIComponent(gid)}`);
  if (generation !== state.generation || state.focus !== gid) return;
  $('nodepanel').innerHTML = `<div class="nl">GID</div><div class="gidbig">${esc(n.gid)}</div><div class="nl">Роль</div><div class="nv">${badge(n.role)}</div><div class="nl">Приоритет проверки</div><div class="nv">${percent(n.priority_score)}</div><div class="nl">Колено / кластер</div><div class="nv">${n.depth} / ${n.cluster_id == null ? '—' : '#' + n.cluster_id}${n.is_seed ? ' · seed' : ''}</div><div class="nl">Вход / выход</div><div class="nv">${money(n.in_kzt)} / ${money(n.out_kzt)}</div><div class="nl">Переводы: вход / выход</div><div class="nv">${n.in_tx ?? '—'} / ${n.out_tx ?? '—'}</div><div class="nl">Обоснование</div><div class="evbox">${esc(n.evidence)}</div>`;
  await loadGraph();
}

async function search() {
  const request = ++state.searchRequest;
  const q = $('gidsearch').value.trim().toLowerCase();
  if (!q || !state.token) { $('searchdd').classList.remove('show'); return; }
  const data = await api(`/ranking/search?q=${encodeURIComponent(q)}&limit=5`);
  if (request !== state.searchRequest || q !== $('gidsearch').value.trim().toLowerCase()) return;
  const roles = Object.keys(ROLES).filter((r) => r.includes(q));
  const clusters = state.clusters.filter((c) => String(c.cluster_id) === q || `кластер ${c.cluster_id}`.includes(q)).slice(0, 4);
  $('searchdd').innerHTML = data.items.map((n) => `<button class="sd-row" data-gid="${esc(n.gid)}"><span class="gid">${esc(n.gid)}</span>${badge(n.role)}</button>`).join('') + roles.map((r) => `<button class="sd-row" data-search-role="${r}">${badge(r)} · очередь</button>`).join('') + clusters.map((c) => `<button class="sd-row" data-cluster="${c.cluster_id}">Кластер #${c.cluster_id} · ${c.n_nodes} узлов</button>`).join('') || '<div class="sd-empty">Ничего не найдено</div>';
  $('searchdd').classList.add('show');
}

function handled(task) { return Promise.resolve().then(task).catch((error) => message(error.message, true)); }
function debounce(fn, delay = 250) { let timer; return () => { clearTimeout(timer); timer = setTimeout(() => handled(fn), delay); }; }

$('role-filters').innerHTML = Object.entries(ROLES).map(([role, color]) => `<label><input type="checkbox" checked value="${role}"><span class="dot" style="background:${color}"></span>${role}</label>`).join('');
Object.keys(ROLES).forEach((r) => $('queue-role').add(new Option(r, r)));
$('role-filters').addEventListener('change', drawGraph);
$('auth-toggle').addEventListener('click', () => {
  state.register = !state.register;
  $('auth-title').textContent = state.register ? 'Создать аккаунт' : 'Вход в MoneyGraph';
  $('auth-submit').textContent = state.register ? 'Зарегистрироваться' : 'Войти';
  $('auth-toggle').textContent = state.register ? 'У меня есть аккаунт' : 'Создать аккаунт';
  $('password').autocomplete = state.register ? 'new-password' : 'current-password';
  $('auth-error').textContent = '';
});
$('auth-form').addEventListener('submit', async (event) => {
  event.preventDefault(); $('auth-error').textContent = ''; $('auth-submit').disabled = true;
  try {
    const result = await api(state.register ? '/auth/register' : '/auth/login', {method: 'POST', body: JSON.stringify({email: $('email').value, password: $('password').value})});
    state.token = result.access_token; sessionStorage.setItem('moneygraph-token', state.token);
    await authenticated();
  } catch (error) { if ($('auth').hidden) message(error.message, true); else $('auth-error').textContent = error.message; }
  finally { $('auth-submit').disabled = false; }
});
$('logout').addEventListener('click', () => showAuth());
document.querySelectorAll('nav [data-v]').forEach((button) => button.addEventListener('click', () => navigate(button.dataset.v)));
action($('refresh'), async () => { message(''); await refresh(); });
action($('analyze'), async () => {
  state.mutating = true; updateActions(); message('Пересчитываем роли, кластеры и очередь проверки…');
  try { await api('/analysis', {method: 'POST'}); await refresh(); message('Анализ обновлён.'); }
  finally { state.mutating = false; updateActions(); }
});
$('upload').addEventListener('click', () => $('dataset-file').click());
$('dataset-file').addEventListener('change', () => handled(async () => {
  const file = $('dataset-file').files[0]; if (!file) return;
  if (file.size > 30 * 1024 * 1024) { $('dataset-file').value = ''; throw new Error('Архив должен быть не больше 30 МБ.'); }
  const body = new FormData(); body.append('file', file);
  state.mutating = true; updateActions(); message('Проверяем архив, загружаем переводы и рассчитываем анализ…');
  try { await api('/dataset/import', {method: 'POST', body}); await refresh(); message('Датасет загружен. Анализ готов.'); }
  finally { $('dataset-file').value = ''; state.mutating = false; updateActions(); }
}));
action($('download'), async () => {
  const filename = $('export-file').value;
  const blob = await api(`/exports/${filename}`, {blob: true});
  const url = URL.createObjectURL(blob), link = document.createElement('a');
  link.href = url; link.download = filename; document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000); message(`Скачан ${filename}.`);
});
$('gidsearch').addEventListener('input', debounce(search));
$('gidsearch').addEventListener('keydown', (event) => { if (event.key === 'Escape') $('searchdd').classList.remove('show'); });
document.addEventListener('click', (event) => {
  if (!event.target.closest('.search-wrap')) $('searchdd').classList.remove('show');
  const node = event.target.closest('[data-gid]');
  const cluster = event.target.closest('[data-cluster]');
  const role = event.target.closest('[data-search-role]');
  if (node || cluster || role) { $('searchdd').classList.remove('show'); $('gidsearch').value = ''; state.searchRequest++; }
  if (node) handled(() => openNode(node.dataset.gid));
  if (cluster) handled(async () => {
    state.cluster = Number(cluster.dataset.cluster); state.focus = null;
    document.querySelectorAll('#role-filters input').forEach((i) => { i.checked = true; });
    $('nodepanel').textContent = 'Выберите узел этого кластера'; navigate('network'); await loadGraph();
  });
  if (role) { $('queue-role').value = role.dataset.searchRole; $('queue-search').value = ''; $('queue-cluster').value = ''; state.queue.skip = 0; navigate('priorities'); handled(loadQueue); }
});
$('netsvg').addEventListener('keydown', (event) => { if (['Enter', ' '].includes(event.key) && event.target.dataset.gid) { event.preventDefault(); handled(() => openNode(event.target.dataset.gid)); } });
action($('graph-reset'), async () => { state.focus = null; state.cluster = null; $('nodepanel').textContent = 'Выберите узел на схеме'; await loadGraph(); });
action($('all-roles'), async () => { document.querySelectorAll('#role-filters input').forEach((i) => { i.checked = true; }); drawGraph(); });
$('graph-hops').addEventListener('change', () => handled(loadGraph));
action($('cluster-queue'), async () => { $('queue-cluster').value = state.cluster; $('queue-role').value = ''; $('queue-search').value = ''; state.queue.skip = 0; navigate('priorities'); await loadQueue(); });
$('queue-search').addEventListener('input', debounce(() => { state.queue.skip = 0; return loadQueue(); }));
for (const id of ['queue-role', 'queue-cluster']) $(id).addEventListener('change', () => { state.queue.skip = 0; handled(loadQueue); });
action($('queue-reset'), async () => { $('queue-search').value = ''; $('queue-role').value = ''; $('queue-cluster').value = ''; state.queue.skip = 0; await loadQueue(); });
// Pagination buttons keep their state from loadQueue; generic busy must not re-enable them.
for (const [id, delta] of [['queue-prev', -50], ['queue-next', 50]]) $(id).addEventListener('click', () => {
  $('queue-prev').disabled = true; $('queue-next').disabled = true;
  state.queue.skip = Math.max(0, state.queue.skip + delta); handled(loadQueue);
});
document.querySelectorAll('th[data-k]').forEach((th) => {
  const sort = () => { state.queue.direction = state.queue.sort === th.dataset.k && state.queue.direction === 'asc' ? 'desc' : 'asc'; state.queue.sort = th.dataset.k; state.queue.skip = 0; handled(loadQueue); };
  th.addEventListener('click', sort); th.addEventListener('keydown', (e) => { if (e.key === 'Enter') sort(); });
});
if (state.token) authenticated().catch((error) => { if ($('auth').hidden && !state.summary) showAuth(error.message); else message(error.message, true); });
else showAuth();
