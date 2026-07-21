#!/usr/bin/env bash
set -euo pipefail

ROOT="${CONTRACTKV_V100_ROOT:-/data/home/${USER}/contractkv_v100}"

if [[ ! -d "$(dirname "$ROOT")" ]]; then
  echo "Parent directory does not exist: $(dirname "$ROOT")" >&2
  exit 2
fi

mkdir -p \
  "$ROOT/code" "$ROOT/models" "$ROOT/env" "$ROOT/protocols" \
  "$ROOT/traces" "$ROOT/pbs" "$ROOT/logs" "$ROOT/results" \
  "$ROOT/cache" "$ROOT/hf_cache" "$ROOT/tmp" "$ROOT/artifacts"

cat <<EOF
ContractKV V100 workspace ready: $ROOT
Use a job-specific cache root in every PBS job:
  $ROOT/cache/\$PBS_JOBID/{triton,torchinductor,vllm}
Do not install CUDA packages into the RHEL system Python.
EOF
