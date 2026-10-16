#!/usr/bin/env bash
# Startup-only compatibility repair. Frozen method/input/source bytes stay intact.
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY=/home/user/miniconda3/envs/contractkv-cu128/bin/python
cd "$ROOT"
export CONTRACTKV_CHECKSUM_COMPAT_ROOT="$ROOT"
"$PY" - <<'PYCODE'
from pathlib import Path
import hashlib,json,shutil
from datetime import datetime,timezone
root=Path.cwd();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
receipt_path=root/'results/tsc_revision_r4/fidelity_checksum_compat_prerun_v4.json'
receipt=json.loads(receipt_path.read_text());assert receipt['public_remote_commit_verified'] and receipt['before_first_new_input_forward']
lf_dir=root/'.artifacts/fidelity_v3_LF_checksums_v4';assert not lf_dir.exists();lf_dir.mkdir()
for condition in ('head','faithful'):
 base=root/f'results/tsc_revision_r4/input_fidelity_development_{condition}_v3'
 assert not list((base/'cells').glob('*/runtime_manifest.json')) and not list((base/'cells').glob('*/raw.jsonl')), 'Preserve actual model attempts; this retry is startup-only'
 freeze=json.loads((base/'freeze.json').read_text());original=base/'source_checksums.sha256'
 before=original.read_bytes();converted=before.replace(b'\r\n',b'\n');assert b'\r' not in converted
 expected={row['path']:row['sha256'] for row in freeze['files']}
 parsed={line.split('  ',1)[1]:line.split('  ',1)[0] for line in converted.decode().splitlines()}
 assert parsed==expected
 for path,digest in expected.items():
  assert sha(root/path)==digest and sha(base/'source_snapshot'/path)==digest
 target=lf_dir/f'{condition}.sha256';target.write_bytes(converted)
 record={'schema_version':'tsc-r4.startup-checksum-compatibility.v4','timestamp_UTC':datetime.now(timezone.utc).isoformat(),
         'primary_freeze_sha256':sha(base/'freeze.json'),'original_checksum_list_sha256':hashlib.sha256(before).hexdigest(),
         'LF_parser_copy_sha256':sha(target),'all_frozen_source_and_snapshot_hashes_verified':len(expected),
         'frozen_bytes_edited':False,'method_input_scoring_or_clock_changed':False,'prior_attempt_model_requests':0,
         'repair':'Windows CRLF checksum-list line endings became filename CR on Linux. Verify an LF-only parser copy with exactly the same path/hash map. All other sha256sum invocations use the original binary.',
         'compatibility_prerun_receipt':receipt}
 with (base/'execution_checksum_compat_v4.json').open('x') as out:json.dump(record,out,indent=2);out.write('\n')
 shutil.copyfile(Path(__file__) if '__file__' in globals() and Path(__file__).is_file() else root/'scripts/run_tsc_revision_r4_fidelity_checksum_compat_v4.sh',base/'execution_checksum_compat_source_v4.sh')
PYCODE
sha256sum() {
  if [[ "$#" == 2 && "$1" == -c ]];then
    case "$2" in
      results/tsc_revision_r4/input_fidelity_development_head_v3/source_checksums.sha256)
        command sha256sum -c "$CONTRACTKV_CHECKSUM_COMPAT_ROOT/.artifacts/fidelity_v3_LF_checksums_v4/head.sha256";return ;;
      results/tsc_revision_r4/input_fidelity_development_faithful_v3/source_checksums.sha256)
        command sha256sum -c "$CONTRACTKV_CHECKSUM_COMPAT_ROOT/.artifacts/fidelity_v3_LF_checksums_v4/faithful.sha256";return ;;
    esac
  fi
  command sha256sum "$@"
}
export -f sha256sum
printf '\nSTARTUP_CHECKSUM_COMPATIBILITY_V4 frozen226bytesunchanged no_prior_model_forward\n'
bash scripts/run_tsc_revision_r4_fidelity_development_v3.sh
