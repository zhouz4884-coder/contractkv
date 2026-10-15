#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
DATA=/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9
PY=/home/user/miniconda3/envs/contractkv-cu128/bin/python
cd "$ROOT"
sha256sum -c results/tsc_revision_r2/batch_reuse_v1/source_checksums.sha256
export PYTHONPATH="$ROOT/third_party/vllm-contractkv-tsc-r1r-slice:$ROOT" PYTHON_BIN="$PY" VLLM_USE_V1=1
export TMPDIR="$DATA/tmp/contractkv-r1r" HF_HOME="$DATA/datasets/hf_cache"
export CONTRACTKV_POLICY_HASH="$(sha256sum results/tsc_revision_r2/batch_reuse_v1/freeze.json | awk '{print $1}')"
export CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000 CONTRACTKV_MAX_DEGRADATION=1000000000
export CONTRACTKV_SHADOW_CHUNK_TOKENS=128 CONTRACTKV_SHADOW_ROUND_TOKENS=128
export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1
export EXTRA_VLLM_ARGS="--enable-prefix-caching --host 127.0.0.1" VLLM_STARTUP_POLLS=360
run_case() (
  name=$1 gpu=$2 port=$3
  case "$name" in
    llama) model="$DATA/models/Llama-3.1-8B-Instruct"; served=llama31-8b ;;
    mistral) model="$DATA/models/Mistral-7B-Instruct-v0.3"; served=mistral7b ;;
  esac
  base="$ROOT/results/tsc_revision_r2/batch_reuse_v1/$name"; mkdir -p "$base"
  [[ ! -e "$base/raw.jsonl" ]] || exit 41
  export CONTRACTKV_PREFIX_METRICS_LOG="$base/metrics.jsonl"
  export VLLM_CACHE_ROOT="$ROOT/cache/tsc_revision_r2/batch_reuse_v1-$name/vllm"
  export TRITON_CACHE_DIR="$ROOT/cache/tsc_revision_r2/batch_reuse_v1-$name/triton"
  export TORCHINDUCTOR_CACHE_DIR="$ROOT/cache/tsc_revision_r2/batch_reuse_v1-$name/inductor"
  "$PY" scripts/tsc_revision_r1r_validation_manifest.py --root "$ROOT" --model "$model" \
    --sessions results/tsc_revision_r1r/inputs/heldout_sealed_sessions_v1.jsonl --cell "r2-development-batch-$name" --output "$base/runtime_manifest.json"
  cleanup() { bash scripts/stop_vllm_server.sh --pid-path "$base/server.pid" --port "$port" || true; }
  trap cleanup EXIT
  bash scripts/run_vllm_server.sh --phase "r2-development-batch-$name" --model-path "$model" --served-model-name "$served" \
    --port "$port" --gpu-ids "$gpu" --tensor-parallel-size 1 --dtype float16 --max-model-len 16384 \
    --max-num-seqs 2 --gpu-memory-utilization .88 --log-path "$ROOT/logs/tsc_revision_r2/batch_reuse_${name}_server.log" --pid-path "$base/server.pid"
  "$PY" scripts/tsc_revision_r2_batch_reuse.py --config configs/tsc_revision_r2_batch_reuse_v1.json \
    --protocol configs/tsc_revision_r1r_validation_protocol_v1.json --sessions results/tsc_revision_r1r/inputs/heldout_sealed_sessions_v1.jsonl \
    --case "$name" --base-url "http://127.0.0.1:$port/v1" --policy-hash "$CONTRACTKV_POLICY_HASH" \
    --output "$base/raw.jsonl" --metrics "$base/metrics.jsonl"
)
run_case llama 0 9894 & p0=$!
run_case mistral 1 9895 & p1=$!
failed=0; wait "$p0" || failed=1; wait "$p1" || failed=1
[[ "$failed" == 0 ]] || exit 31
echo R2_BATCH_REUSE_V1_COMPLETE
