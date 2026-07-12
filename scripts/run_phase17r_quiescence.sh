#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PYTHON_BIN="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
SCHEDULER="${SCHEDULER:-/home/user/miniconda3/envs/contractkv-cu128/lib/python3.10/site-packages/vllm/v1/core/sched/scheduler.py}"
MODEL_PATH="${MODEL_PATH:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-8B}"
PORT="${PORT:-8019}"; cd "$ROOT"; mkdir -p logs/phase17r results/hard_systems
POLICY="results/hard_systems/phase17r_frozen_policy_manifest_v0.json"; REGISTRY="$ROOT/results/hard_systems/phase17r_quiescence_registry.json"; EVENT="$ROOT/results/hard_systems/phase17r_quiescence_events_v0.jsonl"; PID="logs/phase17r/qwen8b_quiescence.pid"
"$PYTHON_BIN" scripts/install_vllm_v1_phase17_hook.py --scheduler "$SCHEDULER" --action install; "$PYTHON_BIN" -m py_compile "$SCHEDULER"; rm -f "$REGISTRY" "$EVENT" "$PID"
export CONTRACTKV_EPHEMERAL_SHADOW=1 CONTRACTKV_QUIESCENCE=1 CONTRACTKV_PHASE17_REGISTRY="$REGISTRY" CONTRACTKV_PHASE16R_EVENT_LOG="$EVENT"
export CONTRACTKV_IDLE_GRACE_MS=10 CONTRACTKV_BASE_BACKOFF_MS=1 CONTRACTKV_MAX_BACKOFF_MS=8 CONTRACTKV_SHADOW_CHUNK_TOKENS=32 CONTRACTKV_SHADOW_ROUND_TOKENS=32 CONTRACTKV_SHADOW_BLOCK_WATERMARK=0
export EXTRA_VLLM_ARGS="--enable-prefix-caching --scheduling-policy priority --enable-chunked-prefill --max-num-batched-tokens 1024"
stop_server(){ [[ -f "$PID" ]] && kill "$(cat "$PID")" 2>/dev/null || true; }; trap stop_server EXIT
bash scripts/run_vllm_server.sh --phase phase17rq --model-path "$MODEL_PATH" --served-model-name qwen3-8b --port "$PORT" --gpu-ids 0 --tensor-parallel-size 1 --dtype float16 --max-model-len 8192 --max-num-seqs 2 --gpu-memory-utilization 0.88 --log-path logs/phase17r/qwen8b_quiescence.log --pid-path "$PID"
"$PYTHON_BIN" scripts/phase17_verifier_quiescence_live.py --base-url "http://127.0.0.1:${PORT}/v1" --model qwen3-8b --model-path "$MODEL_PATH" --policy "$POLICY" --registry "$REGISTRY" --event-log "$EVENT" --raw-output results/hard_systems/phase17r_qwen8b_quiescence_raw_v0.csv --summary-output results/hard_systems/phase17r_qwen8b_quiescence_v0.csv
stop_server; trap - EXIT
