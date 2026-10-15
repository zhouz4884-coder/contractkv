#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
DATA=/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9
PY=/home/user/miniconda3/envs/contractkv-cu128/bin/python
cd "$ROOT"
sha256sum -c results/tsc_revision_r2/margin_smoke_v1/source_checksums.sha256
export PYTHONPATH="$ROOT/third_party/vllm-contractkv-tsc-r2-margin:$ROOT" PYTHON_BIN="$PY" VLLM_USE_V1=1
export TMPDIR="$DATA/tmp/contractkv-r1r" HF_HOME="$DATA/datasets/hf_cache"
export CONTRACTKV_POLICY_HASH="$(sha256sum results/tsc_revision_r2/margin_smoke_v1/freeze.json | awk '{print $1}')"
export CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000 CONTRACTKV_MAX_DEGRADATION=1000000000
export CONTRACTKV_MIN_RAW_TOKEN_MARGIN=.0625 CONTRACTKV_MIN_CANDIDATE_TOKEN_MARGIN=.0625
export CONTRACTKV_SHADOW_CHUNK_TOKENS=128 CONTRACTKV_SHADOW_ROUND_TOKENS=128
export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1
export EXTRA_VLLM_ARGS="--enable-prefix-caching --host 127.0.0.1" VLLM_STARTUP_POLLS=360
run_case() (
  name=$1 gpu=$2 port=$3
  case "$name" in
    llama) model="$DATA/models/Llama-3.1-8B-Instruct"; served=llama31-8b ;;
    mistral) model="$DATA/models/Mistral-7B-Instruct-v0.3"; served=mistral7b ;;
  esac
  base="$ROOT/results/tsc_revision_r2/margin_smoke_v1/$name"; mkdir -p "$base"
  [[ ! -e "$base/raw.jsonl" ]] || exit 41
  export CONTRACTKV_PREFIX_METRICS_LOG="$base/metrics.jsonl"
  export CONTRACTKV_R2_EXECUTION_TRACE="$base/execution_trace.jsonl"
  export CONTRACTKV_R2_VERIFY_TRACE="$base/verify_trace.jsonl"
  export VLLM_CACHE_ROOT="$ROOT/cache/tsc_revision_r2/margin_smoke_v1-$name/vllm"
  export TRITON_CACHE_DIR="$ROOT/cache/tsc_revision_r2/margin_smoke_v1-$name/triton"
  export TORCHINDUCTOR_CACHE_DIR="$ROOT/cache/tsc_revision_r2/margin_smoke_v1-$name/inductor"
  "$PY" scripts/tsc_revision_r2_runtime_manifest.py --root "$ROOT" --model "$model" --freeze results/tsc_revision_r2/margin_smoke_v1/freeze.json --gpu "$gpu" \
    --sessions results/tsc_revision_r1r/inputs/heldout_sealed_sessions_v1.jsonl --cell "r2-margin-preflight-$name" --output "$base/runtime_manifest.json"
  cleanup() { bash scripts/stop_vllm_server.sh --pid-path "$base/server.pid" --port "$port" || true; }
  trap cleanup EXIT
  bash scripts/run_vllm_server.sh --phase "r2-margin-preflight-$name" --model-path "$model" --served-model-name "$served" \
    --port "$port" --gpu-ids "$gpu" --tensor-parallel-size 1 --dtype float16 --max-model-len 16384 \
    --max-num-seqs 1 --gpu-memory-utilization .88 --log-path "$ROOT/logs/tsc_revision_r2/margin_smoke_${name}_server.log" --pid-path "$base/server.pid"
  "$PY" scripts/tsc_revision_r2_margin_smoke.py --config configs/tsc_revision_r2_margin_smoke_v1.json \
    --protocol configs/tsc_revision_r1r_validation_protocol_v1.json --sessions results/tsc_revision_r1r/inputs/heldout_sealed_sessions_v1.jsonl \
    --case "$name" --base-url "http://127.0.0.1:$port/v1" --policy-hash "$CONTRACTKV_POLICY_HASH" \
    --output "$base/raw.jsonl" --metrics "$base/metrics.jsonl"
)
run_case llama 0 9896 & p0=$!
run_case mistral 1 9897 & p1=$!
failed=0; wait "$p0" || failed=1; wait "$p1" || failed=1
[[ "$failed" == 0 ]] || exit 31
echo R2_MARGIN_SMOKE_V1_COMPLETE
