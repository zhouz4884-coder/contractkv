"""Freeze sources and a deterministic template subset before heldout execution."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); a=p.parse_args(); root=a.root
    output=root/'results/tsc_revision_r1r/validation'; output.mkdir(parents=True,exist_ok=True)
    target=output/'freeze_v1.json'
    if target.exists(): raise RuntimeError('Never replace an existing prospective freeze')
    protocol=root/'configs/tsc_revision_r1r_validation_protocol_v1.json'; config=json.loads(protocol.read_text())
    inputs=root/'results/tsc_revision_r1r/inputs'; heldout=inputs/'heldout_sealed_sessions_v1.jsonl'
    if sha(heldout)!=config['heldout_sha256']: raise RuntimeError('Heldout input changed')
    rows=[json.loads(line) for line in heldout.read_text().splitlines() if line.strip()]
    seen=Counter(); selected=[]
    for row in rows:
        fam=row['revision_family']
        if seen[fam]<2: selected.append(row); seen[fam]+=1
    assert len(selected)==10 and set(seen.values())=={2}
    subset=inputs/'heldout_fanout_sessions_v1.jsonl'
    subset.write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in selected))
    files=['configs/tsc_revision_r1r_validation_protocol_v1.json',
           'scripts/tsc_revision_r1r_live.py','scripts/tsc_revision_r1r_query_scope.py',
           'scripts/tsc_revision_r1r_business_stream.py','scripts/tsc_revision_live.py',
           'scripts/tsc_revision_r1r_prefix_smoke.py','scripts/tsc_revision_r1r_validation_manifest.py',
           'scripts/run_tsc_revision_r1r_validation.sh','scripts/tsc_revision_r1r_freeze_validation.py',
           'scripts/contractkv_verifier.py','scripts/phase17_live_common.py',
           'scripts/phase20a_official_quality.py','scripts/phase22_llama_layout_ladder.py',
           'scripts/phase13b_fresh_policy_quality_replay.py','scripts/phase12f_real_vllm_caposc_replay.py',
           'scripts/phase16r_verifier_live.py',str(heldout.relative_to(root)),str(subset.relative_to(root))]
    commitment=json.loads((root/'configs/tsc_revision_r1r_backend_commitment_v2.json').read_text())
    for item in commitment['source_files']:
        path=root/'third_party/vllm-contractkv-tsc-r1r-slice'/item['file']
        if sha(path)!=item['after_sha256']: raise RuntimeError('Backend source changed: '+str(path))
        files.append(str(path.relative_to(root)))
    record={'schema_version':'tsc-r1r.validation-freeze.v1','timestamp':datetime.now(timezone.utc).isoformat(),
            'basis':'development complete; heldout outcomes not opened or used for selection',
            'expected_cells':45,'expected_future_generations':28350,
            'template_subset_source_groups':[row['revision_source_group'] for row in selected],
            'files':[{'path':name,'sha256':sha(root/name)} for name in files]}
    for name in files:
        saved=output/'source_snapshot'/name
        saved.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(root/name,saved)
    target.write_text(json.dumps(record,indent=2)+'\n'); print(json.dumps({'frozen_files':len(files),'freeze_sha256':sha(target)}))


if __name__=='__main__': main()
