#!/usr/bin/env bash
set -euo pipefail

MODEL_ROOT="${MODEL_ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models}"
MODEL_PATH="${MODEL_PATH:-${MODEL_ROOT}/Llama-3.1-8B-Instruct}"
SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-llama3-8b}"
PORT="${PORT:-8001}"
GPU_IDS="${GPU_IDS:-0}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.88}"
MAX_NUM_SEQS="${MAX_NUM_SEQS:-1}"
PROMPTS="${PROMPTS:-configs/llama3_8b_actual_context_prompts.jsonl}"
RAW_CSV="${RAW_CSV:-results/baselines/llama3_8b_actual_context_scaling_raw.csv}"
SUMMARY_CSV="${SUMMARY_CSV:-results/baselines/llama3_8b_actual_context_scaling_summary.csv}"
GPU_MONITOR_DIR="${GPU_MONITOR_DIR:-logs/gpu_monitor}"
COMMIT_HASH="${COMMIT_HASH:-$(git rev-parse --short HEAD 2>/dev/null || echo unknown)}"
REPEAT="${REPEAT:-3}"
WARMUP="${WARMUP:-1}"
TIMEOUT="${TIMEOUT:-240}"

mkdir -p logs/phase3 results/baselines "$GPU_MONITOR_DIR"
rm -f "$RAW_CSV" "$SUMMARY_CSV"

run_one() {
  local target_tokens="$1"
  local max_model_len="$2"
  local kv_capacity="${3:-unknown}"
  local log_path="logs/phase3/llama3_8b_${target_tokens}.log"
  local pid_path="logs/phase3/llama3_8b_${target_tokens}.pid"

  bash scripts/stop_vllm_server.sh --pid-path "$pid_path" || true
  bash scripts/run_vllm_server.sh \
    --phase phase3_llama3_actual_context \
    --model-path "$MODEL_PATH" \
    --served-model-name "$SERVED_MODEL_NAME" \
    --port "$PORT" \
    --gpu-ids "$GPU_IDS" \
    --tensor-parallel-size 1 \
    --dtype float16 \
    --max-model-len "$max_model_len" \
    --max-num-seqs "$MAX_NUM_SEQS" \
    --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION" \
    --log-path "$log_path" \
    --pid-path "$pid_path"

  python scripts/bench_actual_context_scaling.py \
    --base-url "http://127.0.0.1:${PORT}/v1" \
    --model "$SERVED_MODEL_NAME" \
    --prompts "$PROMPTS" \
    --raw-csv "$RAW_CSV" \
    --summary-csv "$SUMMARY_CSV" \
    --configured-max-model-len "$max_model_len" \
    --max-num-seqs "$MAX_NUM_SEQS" \
    --temperature 0 \
    --warmup "$WARMUP" \
    --repeat "$REPEAT" \
    --timeout "$TIMEOUT" \
    --target-tokens "$target_tokens" \
    --log-path "$log_path" \
    --gpu-monitor-dir "$GPU_MONITOR_DIR" \
    --gpu-monitor-prefix phase3_llama3_8b \
    --vllm-kv-capacity "$kv_capacity" \
    --commit-hash "$COMMIT_HASH"

  bash scripts/stop_vllm_server.sh --pid-path "$pid_path" || true
}

run_one 4096 8192
run_one 8192 16384
run_one 16384 32768
run_one 32768 33792
