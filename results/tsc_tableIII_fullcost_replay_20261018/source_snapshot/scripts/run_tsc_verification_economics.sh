#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
SOURCE="${VLLM_SOURCE:-$ROOT/third_party/vllm-contractkv-phase19c}"
SCHEDULER="$SOURCE/vllm/v1/core/sched/scheduler.py"
OUT="$ROOT/results/tsc_service/economics"; LOG="$ROOT/logs/tsc_service/economics"
mkdir -p "$OUT" "$LOG" "$ROOT/cache/tsc-economics"; cd "$ROOT"
export PYTHONPATH="$SOURCE:$ROOT${PYTHONPATH:+:$PYTHONPATH}" VLLM_STARTUP_POLLS="${VLLM_STARTUP_POLLS:-360}"
"$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action install
cleanup_hooks(){ "$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action remove >/dev/null 2>&1 || true; }
trap cleanup_hooks EXIT

run_model(){
  local label=$1 model_path=$2 served=$3 identity=$4 gpu=$5 port=$6
  local raw="$OUT/${label}_boundary_live_v0.csv" contour="$OUT/${label}_break_even_contour_v0.csv"
  [[ -s "$raw" && -s "$contour" && $(head -1 "$raw" | grep -c 'effective_policy') -gt 0 ]] \
    && { echo "SKIP economics $label"; return; }
  rm -f "$raw" "$contour"; local pid="$OUT/${label}.pid"
  cleanup_cell(){ bash scripts/stop_vllm_server.sh --pid-path "$pid" --port "$port" || true; }
  trap cleanup_cell RETURN
  export CONTRACTKV_POLICY_HASH="tsc-economics-$label" CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000 CONTRACTKV_MAX_DEGRADATION=1000000000
  export EXTRA_VLLM_ARGS="--enable-prefix-caching"
  VLLM_CACHE_ROOT="$ROOT/cache/tsc-economics/$label/vllm" TRITON_CACHE_DIR="$ROOT/cache/tsc-economics/$label/triton" \
  bash scripts/run_vllm_server.sh --phase "tsc-economics-$label" --model-path "$model_path" --served-model-name "$served" \
    --port "$port" --gpu-ids "$gpu" --tensor-parallel-size 1 --dtype float16 --max-model-len 8192 \
    --max-num-seqs 8 --gpu-memory-utilization .88 --log-path "$LOG/${label}_server.log" --pid-path "$pid"
  "$PY" scripts/tsc_verification_economics_live.py --tokenizer "$model_path" --model-identity "$identity" \
    --base-url "http://127.0.0.1:$port/v1" --model "$served" --policy-hash "tsc-economics-$label" \
    --raw-output "$raw" --contour-output "$contour"
  cleanup_cell; trap - RETURN
}

run_model qwen /media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-8B qwen3-8b Qwen3-8B 0 8701 & p0=$!
run_model mistral /media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Mistral-7B-Instruct-v0.3 mistral7b Mistral-7B-Instruct-v0.3 1 8702 & p1=$!
failed=0; wait "$p0" || failed=1; wait "$p1" || failed=1; exit "$failed"
