#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
DATA=/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9
PY=/home/user/miniconda3/envs/contractkv-cu128/bin/python
cd "$ROOT"
while ! grep -q R1R_VALIDATION_COMPLETE logs/tsc_revision_r1r/validation_v1.log; do
  if ! kill -0 2334871 2>/dev/null; then echo 'Primary batch stopped before completion; do not start supplemental work'; exit 88; fi
  sleep 30
done
export PYTHONPATH="$ROOT/third_party/vllm-contractkv-tsc-r1r-slice:$ROOT" PYTHON_BIN="$PY" VLLM_USE_V1=1
export TMPDIR="$DATA/tmp/contractkv-r1r" HF_HOME="$DATA/datasets/hf_cache"
export CONTRACTKV_POLICY_HASH="$(sha256sum configs/tsc_revision_r1r_long_horizon_protocol_v1.json | awk '{print $1}')"
export CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000 CONTRACTKV_MAX_DEGRADATION=1000000000
export CONTRACTKV_SHADOW_CHUNK_TOKENS=128 CONTRACTKV_SHADOW_ROUND_TOKENS=128
export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1
export EXTRA_VLLM_ARGS="--enable-prefix-caching --host 127.0.0.1" VLLM_STARTUP_POLLS=360
run_cell() (
  model=$1 repeat=$2 gpu=$3 port=$4
  case "$model" in
    qwen) path="$DATA/models/Qwen3-8B"; served=qwen3-8b ;;
    mistral) path="$DATA/models/Mistral-7B-Instruct-v0.3"; served=mistral7b ;;
    llama) path="$DATA/models/Llama-3.1-8B-Instruct"; served=llama31-8b ;;
  esac
  cell="long-horizon_${model}_r${repeat}"; dir="$ROOT/results/tsc_revision_r1r/long_horizon/$cell"; mkdir -p "$dir"
  [[ ! -e "$dir/raw.jsonl" ]] || exit 41
  export CONTRACTKV_PREFIX_METRICS_LOG="$dir/metrics.jsonl"
  export VLLM_CACHE_ROOT="$ROOT/cache/tsc_revision_r1r/$cell/vllm"
  export TRITON_CACHE_DIR="$ROOT/cache/tsc_revision_r1r/$cell/triton"
  export TORCHINDUCTOR_CACHE_DIR="$ROOT/cache/tsc_revision_r1r/$cell/inductor"
  cleanup() { bash scripts/stop_vllm_server.sh --pid-path "$dir/server.pid" --port "$port" || true; }
  trap cleanup EXIT
  bash scripts/run_vllm_server.sh --phase "$cell" --model-path "$path" --served-model-name "$served" \
    --port "$port" --gpu-ids "$gpu" --tensor-parallel-size 1 --dtype float16 --max-model-len 16384 \
    --max-num-seqs 2 --gpu-memory-utilization .88 --log-path "$ROOT/logs/tsc_revision_r1r/${cell}_server.log" --pid-path "$dir/server.pid"
  "$PY" scripts/tsc_revision_r1r_long_horizon.py --protocol configs/tsc_revision_r1r_long_horizon_protocol_v1.json \
    --model "$served" --base-url "http://127.0.0.1:$port/v1" --repeat "$repeat" --output "$dir/raw.jsonl" --policy-hash "$CONTRACTKV_POLICY_HASH"
)
worker() {
  lane=$1; index=0
  for repeat in 1 2 3; do
    for model in qwen mistral llama; do
      if ((index % 2 == lane)); then run_cell "$model" "$repeat" "$lane" "$((9880+lane))"; fi
      index=$((index+1))
    done
  done
}
worker 0 & p0=$!; worker 1 & p1=$!
failed=0; wait "$p0" || failed=1; wait "$p1" || failed=1
[[ "$failed" == 0 ]] || exit 31
echo R1R_LONG_HORIZON_COMPLETE
