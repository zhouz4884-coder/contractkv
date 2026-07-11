#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PYTHON_BIN="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
SCHEDULER="${SCHEDULER:-/home/user/miniconda3/envs/contractkv-cu128/lib/python3.10/site-packages/vllm/v1/core/sched/scheduler.py}"
MODEL_PATH="${MODEL_PATH:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-4B}"
MODEL_NAME="${MODEL_NAME:-qwen3-4b}"
PORT="${PORT:-8016}"

cd "$ROOT"
mkdir -p logs/phase16 results/hard_systems

if command -v lsof >/dev/null 2>&1; then
  old_pids="$(lsof -t -i ":${PORT}" 2>/dev/null || true)"
  if [[ -n "$old_pids" ]]; then
    kill $old_pids 2>/dev/null || true
    sleep 3
  fi
fi

"$PYTHON_BIN" scripts/install_vllm_v1_ephemeral_shadow_hook.py \
  --scheduler "$SCHEDULER" --action install
"$PYTHON_BIN" -m py_compile "$SCHEDULER"

export CONTRACTKV_EPHEMERAL_SHADOW=1
export CONTRACTKV_SHADOW_CHUNK_TOKENS="${CONTRACTKV_SHADOW_CHUNK_TOKENS:-32}"
export CONTRACTKV_EPHEMERAL_SHADOW_LOG="$ROOT/results/hard_systems/phase16e_qwen3_4b_transaction_events_v0.jsonl"
export CONTRACTKV_PREFIX_METRICS=1
export CONTRACTKV_PREFIX_METRICS_LOG="$ROOT/results/hard_systems/phase16e_qwen3_4b_prefix_events_v0.jsonl"
export EXTRA_VLLM_ARGS="--enable-prefix-caching --scheduling-policy priority --enable-chunked-prefill --max-num-batched-tokens 2048"

bash scripts/run_vllm_server.sh \
  --phase phase16e \
  --model-path "$MODEL_PATH" \
  --served-model-name "$MODEL_NAME" \
  --port "$PORT" \
  --gpu-ids 0 \
  --tensor-parallel-size 1 \
  --dtype float16 \
  --max-model-len 8192 \
  --max-num-seqs 8 \
  --gpu-memory-utilization 0.85 \
  --log-path logs/phase16/phase16e_qwen3_4b_server_final.log \
  --pid-path logs/phase16/phase16e_qwen3_4b_server.pid

"$PYTHON_BIN" scripts/phase16e_live_transactional_slc.py \
  --base-url "http://127.0.0.1:${PORT}/v1" \
  --model "$MODEL_NAME" \
  --prefix-metrics-log results/hard_systems/phase16e_qwen3_4b_prefix_events_v0.jsonl \
  --interference-raw results/hard_systems/phase16e_qwen3_4b_live_interference_raw_v0.csv \
  --interference-summary results/hard_systems/phase16e_qwen3_4b_live_interference_summary_v0.csv \
  --transaction-output results/hard_systems/phase16e_qwen3_4b_live_ephemeral_transaction_v0.csv

kill "$(cat logs/phase16/phase16e_qwen3_4b_server.pid)" 2>/dev/null || true
