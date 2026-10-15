#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
DATA=/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9
PY=/home/user/miniconda3/envs/contractkv-cu128/bin/python
cd "$ROOT"
grep -q R1R_DEVELOPMENT_COMPLETE logs/tsc_revision_r1r/development.log
export PYTHONPATH="$ROOT/third_party/vllm-contractkv-tsc-r1r-slice:$ROOT" PYTHON_BIN="$PY" VLLM_USE_V1=1
export TMPDIR="$DATA/tmp/contractkv-r1r"
export HF_HOME="$DATA/datasets/hf_cache"
export CONTRACTKV_POLICY_HASH="$(sha256sum configs/tsc_revision_r1r_development_protocol_v1.json | awk '{print $1}')"
export CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000 CONTRACTKV_MAX_DEGRADATION=1000000000
export CONTRACTKV_SHADOW_CHUNK_TOKENS=128 CONTRACTKV_SHADOW_ROUND_TOKENS=128
export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1
export EXTRA_VLLM_ARGS="--enable-prefix-caching --host 127.0.0.1" VLLM_STARTUP_POLLS=360
run_cell() (
  model=$1 gpu=$2 port=$3
  case "$model" in
    qwen) path="$DATA/models/Qwen3-8B"; served=qwen3-8b; identity=Qwen3-8B ;;
    mistral) path="$DATA/models/Mistral-7B-Instruct-v0.3"; served=mistral7b; identity=Mistral-7B-Instruct-v0.3 ;;
  esac
  cell="slice-chunk128-development_${model}_query-prefix"
  dir="$ROOT/results/tsc_revision_r1r/cells/$cell"; mkdir -p "$dir"
  [[ ! -e "$dir/raw.jsonl" ]] || { echo "Preserve prior slice attempt"; exit 41; }
  export CONTRACTKV_PREFIX_METRICS_LOG="$dir/metrics.jsonl"
  export VLLM_CACHE_ROOT="$ROOT/cache/tsc_revision_r1r/$cell/vllm"
  export TRITON_CACHE_DIR="$ROOT/cache/tsc_revision_r1r/$cell/triton"
  export TORCHINDUCTOR_CACHE_DIR="$ROOT/cache/tsc_revision_r1r/$cell/inductor"
  cleanup() { bash scripts/stop_vllm_server.sh --pid-path "$dir/server.pid" --port "$port" || true; }
  trap cleanup EXIT
  bash scripts/run_vllm_server.sh --phase "$cell" --model-path "$path" --served-model-name "$served" \
    --port "$port" --gpu-ids "$gpu" --tensor-parallel-size 1 --dtype float16 --max-model-len 16384 \
    --max-num-seqs 2 --gpu-memory-utilization .88 --log-path "$ROOT/logs/tsc_revision_r1r/${cell}_server.log" --pid-path "$dir/server.pid"
  "$PY" scripts/tsc_revision_r1r_prefix_smoke.py --base-url "http://127.0.0.1:$port/v1" --model "$served" \
    --policy-hash "$CONTRACTKV_POLICY_HASH" --repeats 3 --output "$ROOT/results/tsc_revision_r1r/witness-slice-chunk128-smoke-${model}_v3.jsonl"
  "$PY" scripts/tsc_revision_r1r_live.py --protocol configs/tsc_revision_r1r_development_protocol_v1.json \
    --sessions results/tsc_revision_r1r/inputs/development_sessions_v1.jsonl --model "$served" --model-identity "$identity" \
    --policy query-prefix --base-url "http://127.0.0.1:$port/v1" --cell-id "$cell" --policy-hash "$CONTRACTKV_POLICY_HASH" \
    --repeat 3 --output "$dir/raw.jsonl" --summary "$dir/summary.json" --metrics-events "$dir/metrics.jsonl"
)
run_cell qwen 0 9880 & p0=$!
run_cell mistral 1 9881 & p1=$!
failed=0; wait "$p0" || failed=1; wait "$p1" || failed=1
[[ $failed == 0 ]]
echo R1R_WITNESS_SLICE_DEVELOPMENT_COMPLETE
