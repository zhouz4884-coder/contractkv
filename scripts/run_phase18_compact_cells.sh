#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
SRC="${VLLM_SOURCE:-$ROOT/third_party/vllm-contractkv}"
MODEL_PATH="${MODEL_PATH:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-8B}"
PORT="${PORT:-8023}"
CELL="${CELL:-C3}"
SEEDS="${SEEDS:-18101 18102 18103 18104 18105}"
PARKING=0
[[ "$CELL" == "C4" ]] && PARKING=1

cd "$ROOT"
mkdir -p logs/phase18 results/hard_systems

stop_server() {
  if [[ -n "${SERVER_PID:-}" ]]; then
    kill "$SERVER_PID" 2>/dev/null || true
    sleep 3
  fi
  pkill -9 -f "vllm.entrypoints.openai.api_server.*--port $PORT" 2>/dev/null || true
  pkill -9 -f '^VLLM::EngineCore$' 2>/dev/null || true
  pkill -9 -f 'multiprocessing.resource_tracker' 2>/dev/null || true
  while IFS=, read -r gpu_pid gpu_name; do
    gpu_pid="${gpu_pid// /}"
    if [[ "$gpu_name" == *"VLLM::EngineCore"* && -n "$gpu_pid" ]]; then
      kill -9 "$gpu_pid" 2>/dev/null || true
    fi
  done < <(nvidia-smi --query-compute-apps=pid,process_name \
                    --format=csv,noheader,nounits 2>/dev/null || true)
  sleep 3
}

trap stop_server EXIT

for seed in $SEEDS; do
  stop_server
  if ss -ltnp 2>/dev/null | grep -q ":$PORT"; then
    echo "port $PORT remains occupied" >&2
    exit 3
  fi
  if nvidia-smi --query-compute-apps=pid --format=csv,noheader,nounits \
      | grep -q '[0-9]'; then
    echo "GPU compute process remains before seed $seed" >&2
    nvidia-smi --query-compute-apps=pid,process_name,used_memory \
      --format=csv,noheader,nounits >&2
    exit 5
  fi
  LOG="logs/phase18/${CELL,,}_seed_${seed}_server.log"
  EVENT="results/hard_systems/phase18_${CELL,,}_seed_${seed}_events.jsonl"
  RAW="results/hard_systems/phase18_${CELL,,}_seed_${seed}_raw.csv"
  SUMMARY="results/hard_systems/phase18_${CELL,,}_seed_${seed}_summary.csv"
  : > "$EVENT"
  env \
    PYTHONPATH="$SRC:$ROOT" \
    VLLM_USE_V1=1 \
    CONTRACTKV_POLICY_HASH=phase18-c3-policy \
    CONTRACTKV_TRACE_MODE=COUNTERS \
    CONTRACTKV_PARKING="$PARKING" \
    CONTRACTKV_QUIESCENCE=1 \
    CONTRACTKV_IDLE_GRACE_MS=10 \
    CONTRACTKV_BASE_BACKOFF_MS=1 \
    CONTRACTKV_MAX_BACKOFF_MS=8 \
    CONTRACTKV_SHADOW_CHUNK_TOKENS=32 \
    CONTRACTKV_SHADOW_ROUND_TOKENS=32 \
    CONTRACTKV_SHADOW_BLOCK_WATERMARK=0 \
    CUDA_VISIBLE_DEVICES=0 \
    "$PY" -m vllm.entrypoints.openai.api_server \
      --model "$MODEL_PATH" \
      --served-model-name qwen3-8b \
      --dtype float16 \
      --tensor-parallel-size 1 \
      --gpu-memory-utilization 0.88 \
      --max-model-len 8192 \
      --max-num-seqs 2 \
      --enable-prefix-caching \
      --scheduling-policy priority \
      --enable-chunked-prefill \
      --max-num-batched-tokens 1024 \
      --seed "$seed" \
      --port "$PORT" > "$LOG" 2>&1 &
  SERVER_PID=$!
  ready=0
  for _ in $(seq 1 120); do
    if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
      ready=1
      break
    fi
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
      break
    fi
    sleep 2
  done
  if [[ "$ready" != 1 ]]; then
    tail -100 "$LOG" >&2
    exit 4
  fi
  set +e
  "$PY" scripts/phase18_compact_quiescence_live.py \
    --base-url "http://127.0.0.1:$PORT/v1" \
    --model qwen3-8b \
    --cell "$CELL" \
    --seeds "$seed" \
    --active-requests 100 \
    --verifier-requests 4 \
    --warmup-requests 5 \
    --active-gap-ms 2 \
    --event-log "$EVENT" \
    --raw-output "$RAW" \
    --summary-output "$SUMMARY" \
    --timeout 300
  RUN_STATUS=$?
  set -e
  curl -fsS "http://127.0.0.1:$PORT/v1/contractkv/stats" \
    > "results/hard_systems/phase18_${CELL,,}_seed_${seed}_router_stats.json"
  echo "$RUN_STATUS" > "results/hard_systems/phase18_${CELL,,}_seed_${seed}.status"
done

stop_server
trap - EXIT
