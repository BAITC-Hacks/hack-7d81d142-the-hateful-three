"""Read the supplied ZIP without altering it; write reproducible dataset checks."""
from pathlib import Path
from io import BytesIO
from zipfile import ZipFile
import json
import pandas as pd
import numpy as np
import networkx as nx

ROOT = Path(__file__).resolve().parent
with ZipFile(ROOT.parents[1] / 'data (1).zip') as z:
    frames = {name: pd.read_parquet(BytesIO(z.read(f'data/{name}.parquet'))) for name in ['nodes', 'edges', 'transactions']}
n, e, t = (frames[k] for k in ['nodes', 'edges', 'transactions'])
t['date'] = pd.to_datetime(t['date'])
G = nx.DiGraph()
G.add_nodes_from(n.gid)
for r in e.itertuples():
    G.add_edge(r.src, r.dst, sum_kzt=r.sum_kzt, n_tx=r.n_tx)
agg = t.groupby(['src','dst']).agg(amount=('sum_kzt','sum'), count=('sum_kzt','size')).reset_index()
m = e.merge(agg, on=['src','dst'], how='outer', indicator=True)
f = n.copy()
for col, values in [('in_deg',dict(G.in_degree())),('out_deg',dict(G.out_degree())),('in_kzt',dict(G.in_degree(weight='sum_kzt'))),('out_kzt',dict(G.out_degree(weight='sum_kzt')))]:
    f[col] = f.gid.map(values)
f['seed_reach'] = 0
for seed in n.loc[n.is_seed,'gid']:
    f.loc[f.gid.isin(nx.descendants(G, seed)), 'seed_reach'] += 1
dist = nx.multi_source_dijkstra_path_length(G, list(n.loc[n.is_seed,'gid']), weight=None)
daily = t.groupby('date').agg(n_tx=('sum_kzt','size'),sum_kzt=('sum_kzt','sum'))
summary = {
 'tables': {k:{'rows':len(v), 'schema':{c:str(d) for c,d in v.dtypes.items()}, 'nulls':v.isna().sum().to_dict(), 'duplicate_rows':int(v.duplicated().sum())} for k,v in frames.items()},
 'depth_counts':n.depth.value_counts().sort_index().to_dict(),
 'seed_count':int(n.is_seed.sum()), 'date_min':str(t.date.min()), 'date_max':str(t.date.max()),
 'total_transferred_kzt':float(t.sum_kzt.sum()), 'transaction_quantiles':t.sum_kzt.quantile([0,.25,.5,.75,.95,.99,1]).to_dict(),
 'below_5000':int((t.sum_kzt<5000).sum()), 'nonpositive':int((t.sum_kzt<=0).sum()),
 'duplicate_gid':int(n.gid.duplicated().sum()), 'duplicate_pairs':int(e.duplicated(['src','dst']).sum()),
 'unknown_endpoints':len((set(e.src)|set(e.dst))-set(n.gid)),
 'pair_match':m['_merge'].value_counts().to_dict(), 'amount_mismatch':int((~np.isclose(m.sum_kzt,m.amount,rtol=0,atol=.01)).sum()), 'count_mismatch':int((m.n_tx!=m['count']).sum()),
 'isolates':list(nx.isolates(G)), 'isolate_seed_count':int(n[n.gid.isin(list(nx.isolates(G)))].is_seed.sum()),
 'weak_component_sizes':sorted([len(c) for c in nx.weakly_connected_components(G)], reverse=True),
 'strong_components_gt1':sorted([len(c) for c in nx.strongly_connected_components(G) if len(c)>1], reverse=True),
 'self_loops':nx.number_of_selfloops(G),
 'no_outgoing_by_depth':f[f.out_deg==0].groupby('depth').size().to_dict(),
 'depth4_with_outgoing':int(((f.depth==4)&(f.out_deg>0)).sum()),
 'seed_no_incoming':int((f.is_seed&(f.in_deg==0)).sum()),
 'in_degree_3plus':int((f.in_deg>=3).sum()), 'out_degree_10plus':int((f.out_deg>=10).sum()),
 'both_in_and_out':int(((f.in_deg>0)&(f.out_deg>0)).sum()),
 'depth_bfs_mismatch':int((n.gid.map(dist)!=n.depth).sum()),
 'edge_depth_mismatch_src_plus1':int((e.depth != e.src.map(n.set_index('gid').depth)+1).sum()),
 'top_by_in_degree':f.sort_values(['in_deg','in_kzt'],ascending=False).head(5).to_dict('records'),
 'top_by_out_degree':f.sort_values(['out_deg','out_kzt'],ascending=False).head(5).to_dict('records'),
 'top_by_in_amount':f.sort_values('in_kzt',ascending=False).head(5).to_dict('records'),
 'daily':daily.reset_index().assign(date=lambda x:x.date.astype(str)).to_dict('records'),
}
ROOT.mkdir(exist_ok=True)
(ROOT/'profile.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,default=lambda x:x.item() if hasattr(x,'item') else str(x)),encoding='utf-8')
f.to_csv(ROOT/'node_features.csv',index=False)
print(json.dumps(summary,ensure_ascii=False,indent=2,default=lambda x:x.item() if hasattr(x,'item') else str(x)))
