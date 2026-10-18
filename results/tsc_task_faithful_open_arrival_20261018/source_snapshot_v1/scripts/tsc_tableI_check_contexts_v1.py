"""Check exact context duplicates without changing selected samples or clusters."""
from pathlib import Path
from collections import defaultdict,Counter
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]


def context_hash(row):
    body=[{'type':s['type'],'text':s['text']} for s in row['segments']
          if s['type'] not in {'SYS_PROMPT','USER_QUERY','CHAT_HISTORY','TOOL_OBS','SCRATCHPAD'}]
    return hashlib.sha256(json.dumps(body,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def source(row):return row['dataset']+':'+row['task']+':'+str(row['metadata']['source_group_id'])


def main():
    study=ROOT/'results/tsc_tableI_remeasurement_20261018'
    originals=[json.loads(l) for l in (study/'inputs_v1/selected_original_sources_v1.jsonl').open(encoding='utf-8') if l.strip()]
    packed=[json.loads(l) for l in (study/'inputs_v1/selected_packed_sources_v1.jsonl').open(encoding='utf-8') if l.strip()]
    hashes=defaultdict(list);packed_hashes=defaultdict(list)
    for r in originals:hashes[context_hash(r)].append(r['source_group'])
    for r in packed:
        if r['sample'] is not None:packed_hashes[context_hash(r['sample'])].append(r['source_group'])
    aux=json.loads((study/'auxiliary_existing_six_source_v1.json').read_text())
    old_ids=set(aux['independent_source_groups']);old_hashes={}
    for line in (ROOT/'results/workload/phase14d_full_pool_v2.jsonl').open(encoding='utf-8'):
        r=json.loads(line)
        if source(r) in old_ids:old_hashes.setdefault(source(r),context_hash(r))
    assert len(old_hashes)==6
    intersections=[{'old_source':sid,'new_sources':hashes[h]} for sid,h in old_hashes.items() if h in hashes]
    report={'selected_registered_sources':len(originals),'unique_original_context_hashes':len(hashes),
            'unique_packed_context_hashes':len(packed_hashes),
            'exact_original_duplicate_groups':[v for v in hashes.values() if len(v)>1],
            'exact_packed_duplicate_groups':[v for v in packed_hashes.values() if len(v)>1],
            'exact_context_overlap_with_existing_six_sources':intersections,
            'source_replacement_or_primary_cluster_changes':False,
            'not_a_proof_of_semantic_independence_or_production_representativeness':True,
            'new_model_requests':0}
    out=study/'exact_context_identity_audit_v1.json';assert not out.exists()
    out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))


if __name__=='__main__':main()
