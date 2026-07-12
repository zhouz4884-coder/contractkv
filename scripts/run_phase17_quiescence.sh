#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PYTHON_BIN="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
SCHEDULER="${SCHEDULER:-/home/user/miniconda3/envs/contractkv-cu128/lib/python3.10/site-packages/vllm/v1/core/sched/scheduler.py}"
MODEL_PATH="${MODEL_PATH:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-4B}"
PORT=8017
cd "$ROOT"; mkdir -p logs/phase17 results/hard_systems
REGISTRY="$ROOT/results/hard_systems/phase17_quiescence_registry.json"
EVENT="$ROOT/results/hard_systems/phase17_quiescence_events_v0.jsonl"
PID=logs/phase17/phase17_quiescence_server.pid
rm -f "$REGISTRY" "$EVENT" "$PID"
"$PYTHON_BIN" scripts/install_vllm_v1_phase17_hook.py --scheduler "$SCHEDULER" --action install
"$PYTHON_BIN" -m py_compile "$SCHEDULER"
export CONTRACTKV_EPHEMERAL_SHADOW=1 CONTRACTKV_QUIESCENCE=1
export CONTRACTKV_PHASE17_REGISTRY="$REGISTRY" CONTRACTKV_PHASE16R_EVENT_LOG="$EVENT"
export CONTRACTKV_IDLE_GRACE_MS=10 CONTRACTKV_BASE_BACKOFF_MS=1 CONTRACTKV_MAX_BACKOFF_MS=8
export CONTRACTKV_SHADOW_CHUNK_TOKENS=32 CONTRACTKV_SHADOW_BLOCK_WATERMARK=0
export EXTRA_VLLM_ARGS="--enable-prefix-caching --scheduling-policy priority --enable-chunked-prefill --max-num-batched-tokens 2048"
stop(){ [[ -f "$PID" ]] && kill "$(cat "$PID")" 2>/dev/null || true; sleep 3; }
trap stop EXIT
bash scripts/run_vllm_server.sh --phase phase17q --model-path "$MODEL_PATH" --served-model-name qwen3-4b \
  --port "$PORT" --gpu-ids 0 --tensor-parallel-size 1 --dtype float16 --max-model-len 8192 \
  --max-num-seqs 8 --gpu-memory-utilization 0.85 --log-path logs/phase17/phase17_quiescence_server.log --pid-path "$PID"
"$PYTHON_BIN" scripts/phase17_verifier_quiescence_live.py --base-url "http://127.0.0.1:${PORT}/v1" \
  --model qwen3-4b --registry "$REGISTRY" --event-log "$EVENT" \
  --raw-output results/hard_systems/phase17_verifier_quiescence_raw_v0.csv \
  --summary-output results/hard_systems/phase17_verifier_quiescence_summary_v0.csv
stop; trap - EXIT
