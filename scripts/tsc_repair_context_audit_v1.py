"""Exact context identity of independent repair sources; no output selection."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_final_context_disjoint_CPU_v1 import context, rows, source, sha


def main(root):
    study=root/'results/tsc_authorization_task_repair_20261019'
    out=study/'exact_context_audit_v1.json';assert not out.exists()
    prep=json.loads((study/'inputs_v1/preparation_receipt_v1.json').read_text(encoding='utf-8'))
    known=set(prep['excluded_sources_before']);assert len(known)==713
    matches=defaultdict(set);found=set();count=0
    pool=root/'results/workload/phase14d_full_pool_v2.jsonl';assert sha(pool)==prep['source_pool_sha256']
    for row in rows(pool):
        identity=source(row)
        if identity in known:
            matches[context(row)[1]].add(identity);found.add(identity);count+=1
    result=[]
    for row in rows(study/'inputs_v1/original_selected_sessions_v1.jsonl'):
        identity=source(row);assert identity not in known
        typed,flat=context(row)
        result.append(dict(source_group=identity,typed_context_sha256=typed,
                           full_text_context_sha256=flat,known_exact_matches=sorted(matches[flat])))
    assert len(result)==6 and len({r['full_text_context_sha256'] for r in result})==6
    value=dict(status='PASS' if not any(r['known_exact_matches'] for r in result) else 'EXACT_MATCH_FOUND',
        selected=result,known_sources=713,known_records_examined=count,known_sources_found=len(found),
        new_GPU_requests=0,no_replacement_or_answer_or_output_selection=True,
        boundary='Byte-exact whole context deduplication, not semantic or fragment independence.',
        source_sha256=sha(Path(__file__)))
    with out.open('x',encoding='utf-8',newline='\n') as f:json.dump(value,f,indent=2);f.write('\n')
    print(json.dumps(value))


if __name__=='__main__':main(Path.cwd())
