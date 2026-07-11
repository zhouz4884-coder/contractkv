#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PYTHON_BIN="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
SCHEDULER="${SCHEDULER:-/home/user/miniconda3/envs/contractkv-cu128/lib/python3.10/site-packages/vllm/v1/core/sched/scheduler.py}"
MODEL_PATH="${MODEL_PATH:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-4B}"
MODEL_NAME="${MODEL_NAME:-qwen3-4b}"
PORT="${PORT:-8016}"
REGISTRY="$ROOT/results/hard_systems/phase16r_pstp_registry.json"

cd "$ROOT"
mkdir -p logs/phase16r results/hard_systems
"$PYTHON_BIN" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action install
"$PYTHON_BIN" -m py_compile "$SCHEDULER"

stop_server() {
  local pid_file="$1"
  if [[ -f "$pid_file" ]]; then
    kill "$(cat "$pid_file")" 2>/dev/null || true
    for _ in {1..30}; do
      kill -0 "$(cat "$pid_file")" 2>/dev/null || break
      sleep 1
    done
  fi
}
trap 'stop_server logs/phase16r/phase16r_server.pid' EXIT

start_server() {
  local grace="$1"
  local event_log="$2"
  rm -f "$event_log" logs/phase16r/phase16r_server.pid
  export CONTRACTKV_EPHEMERAL_SHADOW=1
  export CONTRACTKV_QUIESCENCE=1
  export CONTRACTKV_PSTP_REGISTRY="$REGISTRY"
  export CONTRACTKV_PHASE16R_EVENT_LOG="$event_log"
  export CONTRACTKV_IDLE_GRACE_MS="$grace"
  export CONTRACTKV_BASE_BACKOFF_MS=1
  export CONTRACTKV_MAX_BACKOFF_MS=8
  export CONTRACTKV_SHADOW_BLOCK_WATERMARK=0
  export CONTRACTKV_SHADOW_CHUNK_TOKENS=32
  export EXTRA_VLLM_ARGS="--enable-prefix-caching --scheduling-policy priority --enable-chunked-prefill --max-num-batched-tokens 2048"
  bash scripts/run_vllm_server.sh \
    --phase phase16r --model-path "$MODEL_PATH" --served-model-name "$MODEL_NAME" \
    --port "$PORT" --gpu-ids 0 --tensor-parallel-size 1 --dtype float16 \
    --max-model-len 8192 --max-num-seqs 8 --gpu-memory-utilization 0.85 \
    --log-path "logs/phase16r/phase16r_grace_${grace}_server.log" \
    --pid-path logs/phase16r/phase16r_server.pid
}

NODE_EVENT="$ROOT/results/hard_systems/phase16r_node_ab_events_v0.jsonl"
PREFIX_EVENT="$ROOT/results/hard_systems/phase16r_prefix_events_v0.jsonl"
rm -f "$NODE_EVENT" "$PREFIX_EVENT" "$REGISTRY"
export CONTRACTKV_PREFIX_METRICS=1
export CONTRACTKV_PREFIX_METRICS_LOG="$PREFIX_EVENT"
if [[ "${SKIP_PHASE16R_AB:-0}" != "1" ]]; then
export CONTRACTKV_PSTP_DOUBLE_FINALIZE=1
start_server 0 "$NODE_EVENT"
"$PYTHON_BIN" scripts/phase16r_pstp_live.py \
  --base-url "http://127.0.0.1:${PORT}/v1" --model "$MODEL_NAME" \
  --registry "$REGISTRY" --event-log "$NODE_EVENT" --prefix-metrics-log "$PREFIX_EVENT" \
  --output results/hard_systems/phase16r_pstp_live_v0.csv
"$PYTHON_BIN" scripts/phase16r_verifier_live.py \
  --base-url "http://127.0.0.1:${PORT}/v1" --model "$MODEL_NAME" \
  --registry "$REGISTRY" --output results/hard_systems/phase16r_verifier_live_v0.csv
stop_server logs/phase16r/phase16r_server.pid
unset CONTRACTKV_PSTP_DOUBLE_FINALIZE
fi

summaries=()
if [[ "${SKIP_PHASE16R_C:-0}" != "1" ]]; then
for grace in ${PHASE16R_GRACES:-0 10 25}; do
  EVENT="$ROOT/results/hard_systems/phase16r_quiescence_grace_${grace}_events_v0.jsonl"
  RAW="$ROOT/results/hard_systems/phase16r_quiescence_grace_${grace}_raw_v0.csv"
  SUMMARY="$ROOT/results/hard_systems/phase16r_quiescence_grace_${grace}_summary_v0.csv"
  start_server "$grace" "$EVENT"
  "$PYTHON_BIN" scripts/phase16r_quiescence_live.py \
    --base-url "http://127.0.0.1:${PORT}/v1" --model "$MODEL_NAME" \
    --registry "$REGISTRY" --event-log "$EVENT" --idle-grace-ms "$grace" \
    --raw-output "$RAW" --summary-output "$SUMMARY"
  stop_server logs/phase16r/phase16r_server.pid
  summaries+=("$SUMMARY")
done
fi

"$PYTHON_BIN" scripts/summarize_phase16r_results.py \
  --quiescence results/hard_systems/phase16r_quiescence_grace_0_summary_v0.csv \
    results/hard_systems/phase16r_quiescence_grace_10_summary_v0.csv \
    results/hard_systems/phase16r_quiescence_grace_25_summary_v0.csv \
  --quiescence-output results/hard_systems/phase16r_quiescence_pareto_v0.csv \
  --historical-input results/end_to_end/phase15_slc_teacher_forced_v2.jsonl \
  --false-safe-output results/hard_systems/phase16r_historical_false_safe_classification_v0.csv \
  --pstp results/hard_systems/phase16r_pstp_live_v0.csv

ps aux | grep -E "vllm|api_server" | grep -v grep || true
nvidia-smi --query-gpu=index,name,memory.used,memory.total --format=csv,noheader
