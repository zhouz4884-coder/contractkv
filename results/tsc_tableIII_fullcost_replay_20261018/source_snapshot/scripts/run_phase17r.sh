#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PYTHON_BIN="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
SCHEDULER="${SCHEDULER:-/home/user/miniconda3/envs/contractkv-cu128/lib/python3.10/site-packages/vllm/v1/core/sched/scheduler.py}"
MODEL_PATH="${MODEL_PATH:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-8B}"
PORT="${PORT:-8018}"
cd "$ROOT"; mkdir -p logs/phase17r results/hard_systems

POLICY="results/hard_systems/phase17r_frozen_policy_manifest_v0.json"
REGISTRY="$ROOT/results/hard_systems/phase17r_runtime_registry.json"
EVENT_LOG="$ROOT/results/hard_systems/phase17r_integrated_events_v0.jsonl"
PID="logs/phase17r/qwen8b_server.pid"
export CONTRACTKV_VERIFIER_CODE_COMMIT="d21e561e81ac0d21c83a8b20ddff1ffa47f96f74"
"$PYTHON_BIN" scripts/contractkv_frozen_policy.py --output "$POLICY" --model-id qwen3-8b --model-path "$MODEL_PATH" --vllm-version 0.10.2 \
  --thresholds results/hard_systems/phase17_frozen_thresholds_v0.json --calibration-csv results/hard_systems/phase17_calibration_candidate_margins_v2.csv --repo "$ROOT"
"$PYTHON_BIN" scripts/install_vllm_v1_phase17_hook.py --scheduler "$SCHEDULER" --action install
"$PYTHON_BIN" -m py_compile "$SCHEDULER"
rm -f "$REGISTRY" "$EVENT_LOG" "$PID"
export CONTRACTKV_EPHEMERAL_SHADOW=1 CONTRACTKV_QUIESCENCE=1 CONTRACTKV_PHASE17_REGISTRY="$REGISTRY" CONTRACTKV_PHASE16R_EVENT_LOG="$EVENT_LOG"
export CONTRACTKV_IDLE_GRACE_MS=10 CONTRACTKV_BASE_BACKOFF_MS=1 CONTRACTKV_MAX_BACKOFF_MS=8 CONTRACTKV_SHADOW_CHUNK_TOKENS=32 CONTRACTKV_SHADOW_ROUND_TOKENS=32 CONTRACTKV_SHADOW_BLOCK_WATERMARK=0 CONTRACTKV_PHASE17_DOUBLE_FINALIZE=1
export EXTRA_VLLM_ARGS="--enable-prefix-caching --scheduling-policy priority --enable-chunked-prefill --max-num-batched-tokens 1024"
stop_server(){ [[ -f "$PID" ]] && kill "$(cat "$PID")" 2>/dev/null || true; }
trap stop_server EXIT
bash scripts/run_vllm_server.sh --phase phase17r --model-path "$MODEL_PATH" --served-model-name qwen3-8b --port "$PORT" --gpu-ids 0 --tensor-parallel-size 1 --dtype float16 --max-model-len 8192 --max-num-seqs 2 --gpu-memory-utilization 0.88 --log-path logs/phase17r/qwen8b_server.log --pid-path "$PID"

AUDIT_STATUS=0
if [[ "${SKIP_PHASE17R_AUDIT:-0}" != "1" ]]; then
  set +e
  "$PYTHON_BIN" scripts/phase17r_false_safe_causality_audit.py --base-url "http://127.0.0.1:${PORT}/v1" --model qwen3-8b --model-path "$MODEL_PATH" --policy "$POLICY" --full-pool results/workload/phase14d_full_pool_v2.jsonl --jobs results/end_to_end/phase14r_quality_jobs_v5.jsonl --labels results/end_to_end/phase14r_quality_labels_v5.csv --output results/hard_systems/phase17r_false_safe_causality_v0.csv --trace-output results/hard_systems/phase17r_false_safe_token_trace_v0.jsonl
  AUDIT_STATUS=$?
  set -e
fi
"$PYTHON_BIN" scripts/phase17r_qwen8b_integrated_live.py --base-url "http://127.0.0.1:${PORT}/v1" --model qwen3-8b --model-path "$MODEL_PATH" --policy "$POLICY" --registry "$REGISTRY" --event-log "$EVENT_LOG" --output results/hard_systems/phase17r_qwen8b_integrated_v0.csv
stop_server; trap - EXIT
echo "false_safe_audit_status=$AUDIT_STATUS"
exit "$AUDIT_STATUS"
