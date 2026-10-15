"""Read-only point-in-time audit of every prospective source/input commitment."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True); args=parser.parse_args()
    root=args.root.resolve(); evidence=root/'results/tsc_revision_r1r'; scopes=[]; failures=[]
    for name in ('validation','long_horizon','known_counterexamples'):
        base=evidence/name; freeze=base/'freeze_v1.json'; declaration=json.loads(freeze.read_text())
        checks=[]
        for item in declaration['files']:
            live=sha(root/item['path']); snapshot=sha(base/'source_snapshot'/item['path'])
            passed=live==snapshot==item['sha256']
            checks.append({'path':item['path'],'expected_sha256':item['sha256'],'current_sha256':live,
                           'snapshot_sha256':snapshot,'matches':passed})
            if not passed: failures.append(name+':'+item['path'])
        scopes.append({'scope':name,'freeze_sha256':sha(freeze),'files_checked':len(checks),'files':checks})
    result={'schema_version':'tsc-r1r.point-in-time-freeze-audit.v1','timestamp':datetime.now(timezone.utc).isoformat(),
            'scopes':scopes,'failures':failures,'all_committed_files_match':not failures,
            'scope':'Current file bytes and immutable snapshots; not proof of uninterrupted historical filesystem state.'}
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'all_committed_files_match':not failures,'files_checked':sum(x['files_checked'] for x in scopes),'failures':failures}))
    return 0 if not failures else 2


if __name__=='__main__': raise SystemExit(main())
