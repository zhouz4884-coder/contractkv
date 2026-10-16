"""Paired source/repeat p99 intervals with weighted order statistics."""
from collections import Counter,defaultdict
import random
import numpy as np
from scripts.tsc_revision_r2_select_policy import percentile


def clustered_tail_ci(pairs,draws=2000,seed=10672129):
    blocks=defaultdict(list)
    for row in pairs:blocks[(row['source_group'],row['repeat'])].append(row)
    sources=sorted({k[0] for k in blocks});repeats=sorted({k[1] for k in blocks})
    keys=[(s,r) for s in sources for r in repeats]
    if set(keys)!=set(blocks) or len({len(blocks[k]) for k in keys})!=1:raise ValueError('Balanced complete paired source/repeat blocks required')
    rng=random.Random(seed);weights=[]
    for _ in range(draws):
        rc=Counter(rng.choices(repeats,k=len(repeats)));sc=Counter(rng.choices(sources,k=len(sources)))
        weights.append([sc[s]*rc[r] for s,r in keys])
    weights=np.asarray(weights,dtype=np.int32);n=len(pairs);x=.99*(n-1);lo=int(x);hi=min(lo+1,n-1)
    def quantile(field):
        observations=sorted((row[field],index) for index,key in enumerate(keys) for row in blocks[key])
        values=np.asarray([x[0] for x in observations]);indices=np.asarray([x[1] for x in observations])
        cumulative=np.cumsum(weights[:,indices],axis=1,dtype=np.int32)
        if not np.all(cumulative[:,-1]==n):raise ValueError('Bootstrap observation count changed')
        low=np.argmax(cumulative>lo,axis=1);high=np.argmax(cumulative>hi,axis=1)
        return values[low]*(hi-x)+values[high]*(x-lo) if hi!=lo else values[low]
    raw=quantile('raw_ready_ttft_ms');policy=quantile('ready_ttft_ms')
    reductions=(100*(1-policy/raw)).tolist()
    return percentile(reductions,.025),percentile(reductions,.975)
