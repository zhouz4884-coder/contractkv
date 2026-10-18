#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
MODEL_PATH="${MODEL_PATH:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Llama-3.1-8B-Instruct}"
SOURCE_VLLM="${SOURCE_VLLM:-$ROOT/third_party/vllm-contractkv-phase19c}"
SCHEDULER="$SOURCE_VLLM/vllm/v1/core/sched/scheduler.py"; PORT="${PORT:-8057}"; GPU="${GPU:-1}"
OUT="$ROOT/results/cross_model/phase20d_cells"; LOG="$ROOT/logs/phase20"
REGISTRY="$OUT/contractkv-two-tier_registry.json"; EVENTS="$OUT/contractkv-two-tier_events.jsonl"
METRICS="$OUT/contractkv-two-tier_metrics.jsonl"; OUTPUT="$OUT/contractkv-two-tier.jsonl"
PID="$LOG/contractkv-two-tier-rerun.pid"; SERVER_LOG="$LOG/contractkv-two-tier-rerun_server.log"
cd "$ROOT"; export PYTHONPATH="$SOURCE_VLLM:$ROOT${PYTHONPATH:+:$PYTHONPATH}"
POLICY_HASH="$("$PY" -c 'import json;print(json.load(open("results/cross_model/phase20c_frozen_two_tier_policy_v0.json"))["policy_hash"])')"
"$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action install
"$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action install
cleanup(){
  bash scripts/stop_vllm_server.sh --pid-path "$PID" --port "$PORT" || true
  "$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action uninstall || true
  "$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action remove || true
}
trap cleanup EXIT
rm -f "$REGISTRY" "$EVENTS" "$METRICS" "$OUTPUT" "$PID"
export CONTRACTKV_EPHEMERAL_SHADOW=1 CONTRACTKV_PSTP_REGISTRY="$REGISTRY" CONTRACTKV_PHASE16R_EVENT_LOG="$EVENTS"
export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1 CONTRACTKV_PREFIX_METRICS_LOG="$METRICS"
export CONTRACTKV_POLICY_HASH="$POLICY_HASH" CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000 CONTRACTKV_MAX_DEGRADATION=1000000000
export EXTRA_VLLM_ARGS="--enable-prefix-caching"
bash scripts/run_vllm_server.sh --phase phase20d-two-tier-fair-rerun --model-path "$MODEL_PATH" --served-model-name llama31-8b \
 --port "$PORT" --gpu-ids "$GPU" --tensor-parallel-size 1 --dtype float16 --max-model-len 8192 --max-num-seqs 2 \
 --gpu-memory-utilization .88 --log-path "$SERVER_LOG" --pid-path "$PID"
"$PY" scripts/phase20d_two_tier_live.py --sessions results/cross_model/phase20d_heldout_sealed_sessions_v0.jsonl \
 --base-url "http://127.0.0.1:$PORT/v1" --model llama31-8b --registry "$REGISTRY" --event-log "$EVENTS" \
 --frozen-policy results/cross_model/phase20c_frozen_two_tier_policy_v0.json --policy-hash "$POLICY_HASH" \
 --concurrency 2 --turns 10 --max-tokens 96 --tool-slack-ms 3000 --metrics-events "$METRICS" --output "$OUTPUT"
"$PY" scripts/phase20d_summarize_one_shot.py --sessions results/cross_model/phase20d_heldout_sealed_sessions_v0.jsonl --tool-slack-ms 3000 \
 --cell "raw-order=$OUT/raw-order.jsonl" --cell "physical-cache-aware=$OUT/physical-cache-aware.jsonl" \
 --cell "tier1-only=$OUT/tier1-only.jsonl" --cell "contractkv-two-tier=$OUTPUT" \
 --summary-output results/cross_model/phase20d_one_shot_summary_v0.csv \
 --quality-output results/cross_model/phase20d_one_shot_official_quality_v0.csv \
 --slo-output results/cross_model/phase20d_one_shot_slo_curve_v0.csv \
 --gate-output results/cross_model/phase20d_one_shot_gate_v0.json
echo PHASE20D_FAIR_RERUN_COMPLETE
