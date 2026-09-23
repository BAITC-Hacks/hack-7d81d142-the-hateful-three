/* A disposable database and browser: no changes to the configured project DB.
 * DATASET_ZIP=/absolute/path/data.zip npm run test:e2e
 * Optional: PYTHON_EXECUTABLE, BROWSER_CHANNEL (default chrome), E2E_PORT.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawn, spawnSync} = require('node:child_process');
const {randomBytes} = require('node:crypto');
const {chromium} = require('playwright');

const root = path.resolve(__dirname, '../..');
const archive = process.env.DATASET_ZIP;
assert(archive && fs.existsSync(archive), 'Set DATASET_ZIP to the supplied data ZIP archive.');
const output = path.join(root, 'output', `e2e-${Date.now()}`);
fs.mkdirSync(output, {recursive: true});
const python = process.env.PYTHON_EXECUTABLE || path.join(root, process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python');
const port = process.env.E2E_PORT || '8767';
const base = `http://127.0.0.1:${port}`;
const env = {...process.env, DATABASE_URL: `sqlite:///${path.join(output, 'test.sqlite3').replaceAll('\\', '/')}`,
  JWT_SECRET_KEY: randomBytes(40).toString('hex'), LOGIN_RATE_LIMIT: '100/minute', REGISTER_RATE_LIMIT: '100/minute', PYTHONIOENCODING: 'utf-8'};
const migration = spawnSync(python, ['-m', 'alembic', 'upgrade', 'head'], {cwd: root, env, encoding: 'utf8'});
assert.equal(migration.status, 0, migration.stderr || String(migration.error));
const serverLog = fs.openSync(path.join(output, 'server.log'), 'w');
const server = spawn(python, ['-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', port, '--no-access-log'], {cwd: root, env, windowsHide: true, stdio: ['ignore', serverLog, serverLog]});
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const checks = [];
let browser;
async function check(name, task) { await task(); checks.push(name); console.log(`PASS ${name}`); }

(async () => {
  try {
    let ready = false;
    for (let i = 0; i < 100; i++) {
      try { if ((await fetch(`${base}/health`)).ok) { ready = true; break; } } catch {}
      await sleep(200);
    }
    assert(ready, 'Test server did not start');
    browser = await chromium.launch({channel: process.env.BROWSER_CHANNEL || 'chrome', headless: true});
    const context = await browser.newContext({baseURL: base, viewport: {width: 1440, height: 1050}, acceptDownloads: true});
    const page = await context.newPage();
    page.setDefaultTimeout(20000);
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    page.on('response', (response) => { if (response.status() >= 500) errors.push(`HTTP ${response.status()} ${response.url()}`); });
    const email = `browser-${Date.now()}@example.com`, password = randomBytes(20).toString('hex');
    let headers, summary, top;
    const api = async (url) => { const result = await page.request.get(url, {headers}); assert(result.ok(), await result.text()); return result.json(); };
    await check('registration and empty database', async () => {
      await page.goto('/');
      await page.getByRole('button', {name: 'Создать аккаунт', exact: true}).click();
      await page.getByLabel('Email', {exact: true}).fill(email);
      await page.getByLabel('Пароль', {exact: true}).fill(password);
      await page.getByRole('button', {name: 'Зарегистрироваться', exact: true}).click();
      await page.locator('#empty-dataset').waitFor({state: 'visible'});
      assert.equal(await page.locator('#kpi-nodes').innerText(), '0');
      headers = {Authorization: `Bearer ${await page.evaluate(() => sessionStorage.getItem('moneygraph-token'))}`};
    });
    await check('invalid archive displays an error without changing data', async () => {
      await page.locator('#dataset-file').setInputFiles({name: 'bad.zip', mimeType: 'application/zip', buffer: Buffer.from('invalid archive')});
      await page.locator('#app-message.error').waitFor();
      assert.equal((await api('/dataset')).nodes, 0);
    });
    await check('real ZIP import, analysis and live KPI values', async () => {
      await page.locator('#dataset-file').setInputFiles(archive);
      await page.getByText('Датасет загружен. Анализ готов.', {exact: true}).waitFor({timeout: 120000});
      summary = await api('/dataset');
      assert(summary.analysis_ready && summary.nodes > 20);
      assert.equal((await page.locator('#kpi-nodes').innerText()).replace(/\s/g, ''), String(summary.nodes));
      assert.equal((await page.locator('#kpi-edges').innerText()).replace(/\s/g, ''), String(summary.edges));
      top = (await api('/ranking/search?limit=100')).items;
      assert.equal(await page.locator('#ov-top [data-gid]').first().getAttribute('data-gid'), top[0].gid);
      await page.screenshot({path: path.join(output, 'overview.png'), fullPage: true});
    });
    await check('queue pagination, server sorting and role filter', async () => {
      await page.getByRole('button', {name: 'Приоритеты', exact: true}).click();
      if (summary.nodes > 50) {
        await page.getByRole('button', {name: 'Далее', exact: true}).click();
        await page.waitForFunction(() => document.querySelector('#queue-page').textContent.startsWith('51'));
        assert.equal(await page.locator('#pq-body [data-gid]').first().getAttribute('data-gid'), top[50].gid);
      }
      await page.locator('th[data-k="priority"]').click();
      const expected = (await api('/ranking/search?sort=priority&direction=asc')).items[0];
      await page.waitForFunction((gid) => document.querySelector('#pq-body [data-gid]')?.dataset.gid === gid, expected.gid);
      await page.locator('#queue-role').selectOption('peripheral');
      await page.waitForFunction(() => [...document.querySelectorAll('#pq-body .role-badge')].every((e) => e.textContent === 'peripheral'));
      assert(await page.locator('#pq-body .role-badge').count() > 0);
    });
    await check('exact large GID search opens the same real node and its edges', async () => {
      const gid = top[Math.min(73, top.length - 1)].gid;
      await page.locator('#gidsearch').fill(gid);
      await page.locator(`#searchdd [data-gid="${gid}"]`).click();
      await page.waitForFunction((id) => document.querySelector('#nodepanel .gidbig')?.textContent === id, gid);
      await page.waitForFunction((id) => !!document.querySelector(`#netsvg [data-gid="${id}"]`), gid);
      const graph = await api(`/graph?gid=${gid}`);
      assert.equal(await page.locator('#netsvg circle[data-gid]').count(), graph.nodes.length);
      assert.equal(await page.locator('#netsvg path[marker-end]').count(), graph.edges.length);
      await page.locator('#graph-hops').selectOption('2');
      const expanded = await api(`/graph?gid=${gid}&hops=2`);
      await page.waitForFunction((count) => document.querySelectorAll('#netsvg circle[data-gid]').length === count, expanded.nodes.length);
      await page.screenshot({path: path.join(output, 'network.png'), fullPage: true});
    });
    await check('cluster opens a real subgraph and filters its queue', async () => {
      await page.getByRole('button', {name: 'Кластеры', exact: true}).click();
      const card = page.locator('.cl-card').first(), cluster = await card.getAttribute('data-cluster');
      await card.click();
      await page.waitForFunction((id) => document.querySelector('#graph-status').textContent.startsWith(`Кластер #${id}`), cluster);
      await page.getByRole('button', {name: 'Очередь этого кластера', exact: true}).click();
      await page.waitForFunction((id) => document.querySelector('#queue-cluster').value === id && [...document.querySelectorAll('#pq-body tr')].every((r) => r.children[4]?.textContent === `#${id}`), cluster);
    });
    await check('all three authenticated CSV downloads', async () => {
      for (const filename of ['nodes_roles.csv', 'clusters.csv', 'top_nodes.csv']) {
        await page.locator('#export-file').selectOption(filename);
        const pending = page.waitForEvent('download');
        await page.getByRole('button', {name: 'Скачать CSV', exact: true}).click();
        const download = await pending;
        assert.equal(download.suggestedFilename(), filename);
        await download.saveAs(path.join(output, filename));
        const csv = fs.readFileSync(path.join(output, filename), 'utf8');
        assert(csv.includes(filename === 'clusters.csv' ? 'cluster_id,n_nodes,n_seed' : 'gid,role'));
        assert(csv.length > 100);
      }
    });
    await check('recalculation and persisted login after reload', async () => {
      await page.getByRole('button', {name: 'Пересчитать анализ', exact: true}).click();
      await page.getByText('Анализ обновлён.', {exact: true}).waitFor({timeout: 120000});
      assert.deepEqual((await api('/ranking/search?limit=100')).items, top);
      await page.reload();
      await page.waitForFunction(() => document.querySelector('#connection-status').textContent.includes('анализ готов'));
      assert.equal(await page.locator('#user-email').innerText(), email);
    });
    await check('unavailable API error and recovery', async () => {
      await page.route('**/dataset', (route) => route.abort());
      await page.getByRole('button', {name: 'Обновить', exact: true}).click();
      await page.locator('#app-message.error').waitFor();
      assert((await page.locator('#app-message').innerText()).includes('Нет связи'));
      await page.unroute('**/dataset');
      await page.getByRole('button', {name: 'Обновить', exact: true}).click();
      await page.waitForFunction(() => document.querySelector('#connection-status').textContent.includes('анализ готов'));
    });
    await check('stored text is escaped and mobile layout stays within viewport', async () => {
      const clusters = await api('/clusters/');
      const patch = await page.request.patch(`/clusters/${clusters[0].id}`, {headers, data: {hypothesis: '<img src=x onerror="window.injected=true">'}});
      assert(patch.ok());
      await page.getByRole('button', {name: 'Обновить', exact: true}).click();
      await page.getByRole('button', {name: 'Кластеры', exact: true}).click();
      await page.getByText('<img src=x onerror="window.injected=true">', {exact: true}).waitFor();
      assert.equal(await page.locator('.cl-card img').count(), 0);
      assert.equal(await page.evaluate(() => window.injected), undefined);
      await page.setViewportSize({width: 390, height: 844});
      for (const name of ['Обзор', 'Сеть', 'Приоритеты', 'Кластеры']) {
        await page.getByRole('button', {name, exact: true}).click();
        const overflow = await page.evaluate(() => ({width: document.documentElement.scrollWidth, viewport: innerWidth,
          elements: [...document.querySelectorAll('body *')].filter((e) => e.getBoundingClientRect().right > innerWidth + 1).map((e) => `${e.tagName}#${e.id}.${e.className}`).slice(0, 8)}));
        assert(overflow.width <= overflow.viewport + 1, `Horizontal page overflow: ${name}: ${JSON.stringify(overflow)}`);
      }
      await page.getByRole('button', {name: 'Обзор', exact: true}).click();
      await page.screenshot({path: path.join(output, 'mobile.png'), fullPage: true});
      await page.setViewportSize({width: 1440, height: 1050});
    });
    await check('expired session clears protected UI and login recovers', async () => {
      await page.evaluate(() => sessionStorage.setItem('moneygraph-token', 'expired-token'));
      await page.reload();
      await page.locator('#auth').waitFor();
      assert(await page.locator('#workspace').isHidden());
      await page.getByLabel('Email', {exact: true}).fill(email);
      await page.getByLabel('Пароль', {exact: true}).fill(password);
      await page.getByRole('button', {name: 'Войти', exact: true}).click();
      await page.waitForFunction(() => document.querySelector('#connection-status').textContent.includes('анализ готов'));
      await page.getByRole('button', {name: 'Выйти', exact: true}).click();
      assert(await page.locator('#workspace').isHidden());
      assert.equal(await page.evaluate(() => sessionStorage.getItem('moneygraph-token')), null);
    });
    assert.deepEqual(errors, [], `Browser/server errors: ${errors.join('; ')}`);
    fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify({checks, summary, errors}, null, 2));
    console.log(`PASS ${checks.length} browser scenarios. Artifacts: ${output}`);
  } catch (error) {
    fs.writeFileSync(path.join(output, 'failure.txt'), error.stack || String(error));
    console.error(error);
    process.exitCode = 1;
  } finally {
    if (browser) await browser.close();
    server.kill();
    fs.closeSync(serverLog);
  }
})();
