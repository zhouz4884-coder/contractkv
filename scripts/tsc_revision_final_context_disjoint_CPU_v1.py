"""Post-selection exact context audit; no source replacement or outcome access."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_build_inputs import source


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def rows(path):
    with path.open(encoding='utf-8') as handle:
        for line in handle:
            if line.strip():yield json.loads(line)
def context(row):
    parts=[dict(type=s.get('type',s.get('segment_type')),text=s['text']) for s in row['segments']
        if s.get('type',s.get('segment_type')) in ('RAG_CHUNK','CODE_CONTEXT','REPO_CONTEXT','CODE_PREFIX','SYNTHETIC_CONTEXT')]
    assert parts
    return hashlib.sha256(json.dumps(parts,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),hashlib.sha256(''.join(s['text'] for s in parts).encode()).hexdigest()


def main(root,output):
    pool=root/'results/workload/phase14d_full_pool_v2.jsonl'
    commitment=json.loads((root/'results/tsc_revision_r4/inputs/input_commitment_v1.json').read_text(encoding='utf-8'))
    assert sha(pool)==commitment['source_pool_sha256']
    exclusion=root/'results/tsc_final_existing_evidence_CPU_20261018/final_known_source_exclusions_v1.json'
    known=set(json.loads(exclusion.read_text(encoding='utf-8'))['excluded_source_groups']);assert len(known)==704
    by_hash=defaultdict(set);by_text=defaultdict(set);known_records=0;found=set()
    for row in rows(pool):
        identity=source(row)
        if identity not in known:continue
        a,b=context(row);by_hash[a].add(identity);by_text[b].add(identity);known_records+=1;found.add(identity)
    entries=[];inputs=[]
    for study in ('tsc_real_repobench_mechanism_20261018','tsc_task_faithful_open_arrival_20261018'):
        path=root/'results'/study/'inputs_v1/original_selected_sessions_v1.jsonl';inputs.append(dict(path=path.relative_to(root).as_posix(),sha256=sha(path)))
        for row in rows(path):
            identity=source(row);assert identity not in known
            a,b=context(row)
            entries.append(dict(study=study,source_group=identity,typed_full_context_sha256=a,concatenated_full_context_sha256=b,
                exact_typed_context_known_source_matches=sorted(by_hash.get(a,[])),
                exact_concatenated_context_known_source_matches=sorted(by_text.get(b,[]))))
    assert len(entries)==9 and len({r['source_group'] for r in entries})==9
    result=dict(schema_version='contractkv.final-context-disjoint-CPU.v1',selected_sources=entries,known_source_groups=704,
        known_source_pool_records_indexed=known_records,
        known_source_groups_found_in_pool=len(found),known_source_groups_not_in_pool=sorted(known-found),
        all_nine_exact_contexts_distinct=len({r['concatenated_full_context_sha256'] for r in entries})==9,
        selected_contexts_with_exact_known_match=sum(bool(r['exact_concatenated_context_known_source_matches']) for r in entries),
        source_pool_sha256=sha(pool),known_exclusion_sha256=sha(exclusion),selected_inputs=inputs,
        no_answer_or_output_inspection=True,no_source_replacement=True,new_GPU_requests=0,
        boundary='Exact preserved context bytes, ignoring questions and system instructions; not semantic deduplication or proof of independence of all code fragments. Known-source pool records may include unexecuted members of an already excluded group.')
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as handle:json.dump(result,handle,indent=2);handle.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('selected_sources','selected_inputs')}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();main(args.root.resolve(),args.output)
