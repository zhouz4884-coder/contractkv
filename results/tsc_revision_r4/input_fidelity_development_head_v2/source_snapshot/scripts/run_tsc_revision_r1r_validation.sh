#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
DATA=/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9
PY=/home/user/miniconda3/envs/contractkv-cu128/bin/python
cd "$ROOT"
export PYTHONPATH="$ROOT/third_party/vllm-contractkv-tsc-r1r-slice:$ROOT" PYTHON_BIN="$PY" VLLM_USE_V1=1
export TMPDIR="$DATA/tmp/contractkv-r1r" HF_HOME="$DATA/datasets/hf_cache"
export CONTRACTKV_POLICY_HASH="$(sha256sum configs/tsc_revision_r1r_validation_protocol_v1.json | awk '{print $1}')"
export CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000 CONTRACTKV_MAX_DEGRADATION=1000000000
export CONTRACTKV_SHADOW_CHUNK_TOKENS=128 CONTRACTKV_SHADOW_ROUND_TOKENS=128
export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1
export EXTRA_VLLM_ARGS="--enable-prefix-caching --host 127.0.0.1" VLLM_STARTUP_POLLS=360
run_cell() (
  study=$1 model=$2 policy=$3 repeat=$4 tenants=$5 gpu=$6 port=$7
  case "$model" in
    qwen) path="$DATA/models/Qwen3-8B"; served=qwen3-8b; identity=Qwen3-8B ;;
    mistral) path="$DATA/models/Mistral-7B-Instruct-v0.3"; served=mistral7b; identity=Mistral-7B-Instruct-v0.3 ;;
    llama) path="$DATA/models/Llama-3.1-8B-Instruct"; served=llama31-8b; identity=Llama-3.1-8B-Instruct ;;
  esac
  cell="${study}_${model}_${policy}_r${repeat}"
  dir="$ROOT/results/tsc_revision_r1r/validation/cells/$cell"
  [[ ! -e "$dir/raw.jsonl" ]] || { echo "Preserve prior attempt: $cell"; exit 41; }
  mkdir -p "$dir"
  sessions="$ROOT/results/tsc_revision_r1r/inputs/heldout_sealed_sessions_v1.jsonl"
  if [[ "$study" == template-fanout ]]; then sessions="$ROOT/results/tsc_revision_r1r/inputs/heldout_fanout_sessions_v1.jsonl"; fi
  export CONTRACTKV_PREFIX_METRICS_LOG="$dir/metrics.jsonl"
  export VLLM_CACHE_ROOT="$ROOT/cache/tsc_revision_r1r/$cell/vllm"
  export TRITON_CACHE_DIR="$ROOT/cache/tsc_revision_r1r/$cell/triton"
  export TORCHINDUCTOR_CACHE_DIR="$ROOT/cache/tsc_revision_r1r/$cell/inductor"
  "$PY" scripts/tsc_revision_r1r_validation_manifest.py --root "$ROOT" --model "$path" --sessions "$sessions" --cell "$cell" --output "$dir/manifest.json"
  cleanup() { bash scripts/stop_vllm_server.sh --pid-path "$dir/server.pid" --port "$port" || true; }
  trap cleanup EXIT
  bash scripts/run_vllm_server.sh --phase "$cell" --model-path "$path" --served-model-name "$served" \
    --port "$port" --gpu-ids "$gpu" --tensor-parallel-size 1 --dtype float16 --max-model-len 16384 \
    --max-num-seqs 2 --gpu-memory-utilization .88 --log-path "$ROOT/logs/tsc_revision_r1r/${cell}_server.log" --pid-path "$dir/server.pid"
  "$PY" scripts/tsc_revision_r1r_prefix_smoke.py --base-url "http://127.0.0.1:$port/v1" --model "$served" \
    --policy-hash "$CONTRACTKV_POLICY_HASH" --repeats 1 --output "$dir/pre_measurement_control.jsonl"
  "$PY" scripts/tsc_revision_r1r_live.py --protocol configs/tsc_revision_r1r_validation_protocol_v1.json \
    --sessions "$sessions" --model "$served" --model-identity "$identity" --study "$study" \
    --policy "$policy" --base-url "http://127.0.0.1:$port/v1" --cell-id "$cell" --policy-hash "$CONTRACTKV_POLICY_HASH" \
    --repeat "$repeat" --tenants-per-template "$tenants" --output "$dir/raw.jsonl" --summary "$dir/summary.json" --metrics-events "$dir/metrics.jsonl"
  echo "R1R_VALIDATION_CELL_COMPLETE $cell"
)
worker() {
  lane=$1; index=0
  for study in single-session template-fanout; do
    tenants=1; [[ "$study" == template-fanout ]] && tenants=10
    for repeat in 1 2 3; do
      case "$repeat" in
        1) policies=(raw-order query-full query-prefix) ;;
        2) policies=(query-prefix raw-order query-full) ;;
        3) policies=(query-full query-prefix raw-order) ;;
      esac
      for policy in "${policies[@]}"; do
        [[ "$study" == template-fanout && "$policy" == query-full ]] && continue
        for model in qwen mistral llama; do
          if (( index % 2 == lane )); then run_cell "$study" "$model" "$policy" "$repeat" "$tenants" "$lane" "$((9880+lane))"; fi
          index=$((index+1))
        done
      done
    done
  done
}
worker 0 & p0=$!
worker 1 & p1=$!
failed=0; wait "$p0" || failed=1; wait "$p1" || failed=1
[[ "$failed" == 0 ]] || exit 31
echo R1R_VALIDATION_COMPLETE
