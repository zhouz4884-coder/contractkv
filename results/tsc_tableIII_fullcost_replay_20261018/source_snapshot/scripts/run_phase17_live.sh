#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PYTHON_BIN="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
SCHEDULER="${SCHEDULER:-/home/user/miniconda3/envs/contractkv-cu128/lib/python3.10/site-packages/vllm/v1/core/sched/scheduler.py}"
MODEL_PATH="${MODEL_PATH:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-4B}"
MODEL_NAME="${MODEL_NAME:-qwen3-4b}"
PORT="${PORT:-8017}"
REGISTRY="$ROOT/results/hard_systems/phase17_runtime_registry.json"
EVENT_LOG="$ROOT/results/hard_systems/phase17_integrated_events_v0.jsonl"
PREFIX_LOG="$ROOT/results/hard_systems/phase17_prefix_events_v0.jsonl"
PID_FILE="logs/phase17/phase17_server.pid"

cd "$ROOT"
mkdir -p logs/phase17 results/hard_systems
"$PYTHON_BIN" scripts/install_vllm_v1_phase17_hook.py --scheduler "$SCHEDULER" --action install
"$PYTHON_BIN" -m py_compile "$SCHEDULER"
rm -f "$REGISTRY" "$EVENT_LOG" "$PREFIX_LOG" "$PID_FILE"

export CONTRACTKV_EPHEMERAL_SHADOW=1
export CONTRACTKV_QUIESCENCE=1
export CONTRACTKV_PHASE17_REGISTRY="$REGISTRY"
export CONTRACTKV_PHASE16R_EVENT_LOG="$EVENT_LOG"
export CONTRACTKV_PREFIX_METRICS=1
export CONTRACTKV_PREFIX_METRICS_LOG="$PREFIX_LOG"
export CONTRACTKV_IDLE_GRACE_MS=10
export CONTRACTKV_BASE_BACKOFF_MS=1
export CONTRACTKV_MAX_BACKOFF_MS=8
export CONTRACTKV_SHADOW_CHUNK_TOKENS=32
export CONTRACTKV_SHADOW_BLOCK_WATERMARK=0
export CONTRACTKV_PHASE17_DOUBLE_FINALIZE=1
export EXTRA_VLLM_ARGS="--enable-prefix-caching --scheduling-policy priority --enable-chunked-prefill --max-num-batched-tokens 2048"

stop_server() {
  if [[ -f "$PID_FILE" ]]; then
    kill "$(cat "$PID_FILE")" 2>/dev/null || true
    for _ in {1..30}; do
      kill -0 "$(cat "$PID_FILE")" 2>/dev/null || break
      sleep 1
    done
  fi
}
trap stop_server EXIT

bash scripts/run_vllm_server.sh \
  --phase phase17 --model-path "$MODEL_PATH" --served-model-name "$MODEL_NAME" \
  --port "$PORT" --gpu-ids 0 --tensor-parallel-size 1 --dtype float16 \
  --max-model-len 8192 --max-num-seqs 8 --gpu-memory-utilization 0.85 \
  --log-path logs/phase17/phase17_server.log --pid-path "$PID_FILE"

if [[ "${SKIP_PHASE17_INTEGRATION:-0}" != "1" ]]; then
"$PYTHON_BIN" scripts/phase17_integrated_live.py \
  --base-url "http://127.0.0.1:${PORT}/v1" --model "$MODEL_NAME" \
  --model-id "$MODEL_NAME" --model-path "$MODEL_PATH" --vllm-version 0.10.2 \
  --registry "$REGISTRY" --event-log "$EVENT_LOG" --prefix-metrics-log "$PREFIX_LOG" \
  --output results/hard_systems/phase17_integrated_live_v0.csv
fi

if [[ "${SKIP_PHASE17_FAULTS:-0}" != "1" ]]; then
"$PYTHON_BIN" scripts/phase17_concurrency_fault_live.py \
  --base-url "http://127.0.0.1:${PORT}/v1" --model "$MODEL_NAME" \
  --model-id "$MODEL_NAME" --model-path "$MODEL_PATH" --vllm-version 0.10.2 \
  --registry "$REGISTRY" --event-log "$EVENT_LOG" \
  --output results/hard_systems/phase17_concurrency_fault_v0.csv
fi

stop_server
trap - EXIT
nvidia-smi --query-gpu=index,name,memory.used,memory.total --format=csv,noheader
