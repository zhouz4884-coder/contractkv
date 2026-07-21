#!/usr/bin/env bash
set -euo pipefail

if [[ $# -eq 0 ]]; then
  echo "usage: $0 <command> [args...]" >&2
  exit 2
fi

ROOT="${CONTRACTKV_V100_ROOT:-/data/home/${USER}/contractkv_v100}"
JOB_TAG="${PBS_JOBID:-manual-$(date +%s)}"
export TMPDIR="$ROOT/tmp/$JOB_TAG"
export HF_HOME="$ROOT/hf_cache"
export TRANSFORMERS_CACHE="$HF_HOME/transformers"
export TRITON_CACHE_DIR="$ROOT/cache/$JOB_TAG/triton"
export TORCHINDUCTOR_CACHE_DIR="$ROOT/cache/$JOB_TAG/torchinductor"
export VLLM_CACHE_ROOT="$ROOT/cache/$JOB_TAG/vllm"
mkdir -p "$TMPDIR" "$TRANSFORMERS_CACHE" "$TRITON_CACHE_DIR" \
  "$TORCHINDUCTOR_CACHE_DIR" "$VLLM_CACHE_ROOT"

exec "$@"
