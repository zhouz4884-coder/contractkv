from collections import defaultdict
import random
import pytest
from scripts.tsc_revision_r2_tail_bootstrap import clustered_tail_ci
from scripts.tsc_revision_r2_select_policy import percentile

def test_weighted_quantile_matches_literal_cluster_resampling():
    pairs=[{'source_group':s,'repeat':r,'raw_ready_ttft_ms':100+i*7+r*3+j,'ready_ttft_ms':60+i*11+r*2+j} for i,s in enumerate('abc') for r in (1,2) for j in (0,1)]
    blocks=defaultdict(list)
    for row in pairs:blocks[(row['source_group'],row['repeat'])].append(row)
    rng=random.Random(14);values=[]
    for _ in range(200):
        repeats=rng.choices([1,2],k=2);sources=rng.choices(list('abc'),k=3)
        expanded=[row for s in sources for r in repeats for row in blocks[(s,r)]]
        raw=percentile([r['raw_ready_ttft_ms'] for r in expanded],.99);policy=percentile([r['ready_ttft_ms'] for r in expanded],.99)
        values.append(100*(1-policy/raw))
    expected=(percentile(values,.025),percentile(values,.975))
    assert clustered_tail_ci(pairs,draws=200,seed=14)==pytest.approx(expected,abs=1e-10)
