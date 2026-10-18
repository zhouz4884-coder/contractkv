#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
MODEL_PATH="${MODEL_PATH:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Llama-3.1-8B-Instruct}"
SOURCE_VLLM="${SOURCE_VLLM:-$ROOT/third_party/vllm-contractkv-phase19c}"
SCHEDULER="$SOURCE_VLLM/vllm/v1/core/sched/scheduler.py"
PORT="${PORT:-8051}"; GPU="${GPU:-0}"
REGISTRY="$ROOT/results/cross_model/phase20c_pstp_registry_v0.json"
EVENTS="$ROOT/results/cross_model/phase20c_pstp_events_v0.jsonl"
METRICS="$ROOT/results/cross_model/phase20c_prefix_metrics_v0.jsonl"
PID="$ROOT/logs/phase20/phase20c_server.pid"; LOG="$ROOT/logs/phase20/phase20c_server.log"
cd "$ROOT"; mkdir -p logs/phase20 results/cross_model
export PYTHONPATH="$SOURCE_VLLM:$ROOT${PYTHONPATH:+:$PYTHONPATH}"

"$PY" scripts/phase20d_build_fresh_split.py \
  --full-pool results/workload/phase14d_full_pool_v2.jsonl \
  --phase19a-quality results/quality/phase19a_frozen_quality_v0.csv \
  --prior-sessions results/end_to_end/phase19b_untouched_sessions_v0.jsonl \
  --prior-sessions results/cross_model/phase19c_calibration_sessions_v0.jsonl \
  --prior-sessions results/cross_model/phase19c_heldout_sessions_v0.jsonl \
  --development-output results/cross_model/phase20d_development_sessions_v0.jsonl \
  --heldout-output results/cross_model/phase20d_heldout_sealed_sessions_v0.jsonl \
  --commitment-output results/cross_model/phase20d_split_commitment_v0.json

"$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action install
"$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action install
"$PY" -m py_compile "$SCHEDULER"
cleanup(){
  bash scripts/stop_vllm_server.sh --pid-path "$PID" --port "$PORT" || true
  "$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action uninstall || true
  "$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action remove || true
}
trap cleanup EXIT
rm -f "$REGISTRY" "$EVENTS" "$METRICS" "$PID"
export CONTRACTKV_EPHEMERAL_SHADOW=1 CONTRACTKV_PSTP_REGISTRY="$REGISTRY"
export CONTRACTKV_PHASE16R_EVENT_LOG="$EVENTS" CONTRACTKV_PREFIX_METRICS=1
export CONTRACTKV_PREFIX_INITIAL_ONLY=1 CONTRACTKV_PREFIX_METRICS_LOG="$METRICS"
export CONTRACTKV_POLICY_HASH="$("$PY" -c 'import json;print(json.load(open("results/cross_model/phase19c_frozen_policy_v0.json"))["policy_hash"])')"
export CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000 CONTRACTKV_MAX_DEGRADATION=1000000000
export EXTRA_VLLM_ARGS="--enable-prefix-caching"
bash scripts/run_vllm_server.sh --phase phase20c --model-path "$MODEL_PATH" --served-model-name llama31-8b \
  --port "$PORT" --gpu-ids "$GPU" --tensor-parallel-size 1 --dtype float16 --max-model-len 8192 \
  --max-num-seqs 2 --gpu-memory-utilization .88 --log-path "$LOG" --pid-path "$PID"
"$PY" scripts/phase20c_two_tier_development.py \
  --sessions results/cross_model/phase20d_development_sessions_v0.jsonl \
  --base-url "http://127.0.0.1:$PORT/v1" --model llama31-8b --registry "$REGISTRY" \
  --policy-hash "$CONTRACTKV_POLICY_HASH" --tool-slack-ms 3000 \
  --output results/cross_model/phase20c_development_two_tier_v0.jsonl
"$PY" scripts/phase20c_freeze_two_tier_policy.py \
  --development-results results/cross_model/phase20c_development_two_tier_v0.jsonl \
  --split-commitment results/cross_model/phase20d_split_commitment_v0.json \
  --model-id llama-3.1-8b-instruct --tool-slack-ms 3000 --guard-ms 100 \
  --output results/cross_model/phase20c_frozen_two_tier_policy_v0.json
"$PY" scripts/phase20c_summarize_two_tier.py \
  --results results/cross_model/phase20c_development_two_tier_v0.jsonl --events "$EVENTS" \
  --policy results/cross_model/phase20c_frozen_two_tier_policy_v0.json \
  --output results/cross_model/phase20c_two_tier_development_summary_v0.json
echo PHASE20C_COMPLETE
