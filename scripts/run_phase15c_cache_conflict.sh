#!/usr/bin/env bash
# Fresh-process Phase 15C cache-state conflict cells.
set -euo pipefail

ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PYTHON_BIN="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
MODEL_PATH="${MODEL_PATH:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-8B}"
OUT="${OUT:-$ROOT/results/hard_systems/phase15c_conflict_cells}"
GPU_IDS="${GPU_IDS:-0}"
PORT="${PORT:-8001}"
SEED="${SEED:-15301}"
POLICIES="${POLICIES:-raw-order static-posc logical-ledger-caposc physical-residency-caposc}"

cd "$ROOT"
mkdir -p "$OUT"
pid_path=""
cleanup() { [[ -z "$pid_path" ]] || bash scripts/stop_vllm_server.sh --pid-path "$pid_path" --port "$PORT" || true; }
trap cleanup EXIT

for policy in $POLICIES; do
  cell="phase15c_s${SEED}_${policy}"
  metrics="$OUT/${cell}_metrics.jsonl"
  log="$OUT/${cell}_server.log"
  pid_path="$OUT/${cell}.pid"
  raw="$OUT/${cell}_raw.csv"
  summary="$OUT/${cell}_summary.csv"
  [[ -s "$summary" ]] && { echo "SKIP completed cell=$cell"; continue; }
  rm -f "$metrics" "$log" "$pid_path" "$raw" "$summary"
  export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_METRICS_LOG="$metrics"
  export EXTRA_VLLM_ARGS="--enable-prefix-caching"
  bash scripts/run_vllm_server.sh --phase phase15c-cache-conflict --model-path "$MODEL_PATH" --served-model-name qwen3-8b \
    --port "$PORT" --gpu-ids "$GPU_IDS" --tensor-parallel-size 1 --dtype float16 --max-model-len 8192 --max-num-seqs 1 \
    --gpu-memory-utilization 0.88 --log-path "$log" --pid-path "$pid_path"
  "$PYTHON_BIN" scripts/phase15c_cache_state_conflict.py --policy "$policy" --seed "$SEED" --turns 100 \
    --component-tokens 2048 --tokenizer "$MODEL_PATH" --metrics-events "$metrics" \
    --base-url "http://127.0.0.1:${PORT}/v1" --model qwen3-8b --raw-output "$raw" --summary-output "$summary"
  bash scripts/stop_vllm_server.sh --pid-path "$pid_path" --port "$PORT" || true
  pid_path=""
done
