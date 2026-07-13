#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
MODEL_PATH="${MODEL_PATH:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Llama-3.1-8B-Instruct}"
SOURCE_VLLM="${SOURCE_VLLM:-$ROOT/third_party/vllm-contractkv-phase19c}"
PORT="${PORT:-8060}"; GPU="${GPU:-0}"
POLICY_HASH="99f7fc72eb233f8ddce48ba7ccbdea68ae5ad398919b4eaeece483c6c44312fc"
PID="$ROOT/logs/phase21a/llama-future-recertification.pid"
LOG="$ROOT/logs/phase21a/llama-future-recertification.log"
cd "$ROOT"; mkdir -p logs/phase21a results/cross_model
export PYTHONPATH="$SOURCE_VLLM:$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export CONTRACTKV_POLICY_HASH="$POLICY_HASH" CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000
export CONTRACTKV_MAX_DEGRADATION=1000000000 EXTRA_VLLM_ARGS="--enable-prefix-caching"
"$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SOURCE_VLLM/vllm/v1/core/sched/scheduler.py" --action install
cleanup(){
  bash scripts/stop_vllm_server.sh --pid-path "$PID" --port "$PORT" || true
  "$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SOURCE_VLLM/vllm/v1/core/sched/scheduler.py" --action remove || true
}
trap cleanup EXIT
bash scripts/run_vllm_server.sh --phase phase21a-llama-future-recertification \
  --model-path "$MODEL_PATH" --served-model-name llama31-8b --port "$PORT" --gpu-ids "$GPU" \
  --tensor-parallel-size 1 --dtype float16 --max-model-len 8192 --max-num-seqs 2 \
  --gpu-memory-utilization .88 --log-path "$LOG" --pid-path "$PID"
"$PY" scripts/phase21a_llama_future_turn_recertification_audit.py \
  --sessions results/cross_model/phase20d_heldout_sealed_sessions_v0.jsonl \
  --causality results/cross_model/phase20d_quality_causality_audit_v0.csv \
  --phase20-output results/cross_model/phase20d_cells/contractkv-two-tier.jsonl \
  --base-url "http://127.0.0.1:$PORT/v1" --model llama31-8b --policy-hash "$POLICY_HASH" \
  --max-tokens 96 --output results/cross_model/phase21a_llama_future_turn_audit_v0.csv \
  --summary-output results/cross_model/phase21a_llama_future_turn_summary_v0.json
echo PHASE21A_COMPLETE
