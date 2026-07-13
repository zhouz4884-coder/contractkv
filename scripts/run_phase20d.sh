#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
MODEL_PATH="${MODEL_PATH:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Llama-3.1-8B-Instruct}"
SOURCE_VLLM="${SOURCE_VLLM:-$ROOT/third_party/vllm-contractkv-phase19c}"
SCHEDULER="$SOURCE_VLLM/vllm/v1/core/sched/scheduler.py"
OUT="$ROOT/results/cross_model/phase20d_cells"; LOG="$ROOT/logs/phase20"
SESSIONS="$ROOT/results/cross_model/phase20d_heldout_sealed_sessions_v0.jsonl"
FROZEN="$ROOT/results/cross_model/phase20c_frozen_two_tier_policy_v0.json"
cd "$ROOT"; mkdir -p "$OUT" "$LOG" results/cross_model
export PYTHONPATH="$SOURCE_VLLM:$ROOT${PYTHONPATH:+:$PYTHONPATH}"
POLICY_HASH="$("$PY" -c 'import json;print(json.load(open("results/cross_model/phase20c_frozen_two_tier_policy_v0.json"))["policy_hash"])')"

"$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action install
"$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action install
"$PY" -m py_compile "$SCHEDULER"
cleanup_source(){
  "$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action uninstall || true
  "$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action remove || true
}
trap cleanup_source EXIT

run_cell(){
  local name=$1 mode=$2 gpu=$3 port=$4
  (
    set -euo pipefail
    local metrics="$OUT/${name}_metrics.jsonl" events="$OUT/${name}_events.jsonl"
    local registry="$OUT/${name}_registry.json" output="$OUT/${name}.jsonl"
    local pid="$LOG/${name}.pid" log="$LOG/${name}_server.log"
    rm -f "$metrics" "$events" "$registry" "$output" "$pid"
    export CONTRACTKV_EPHEMERAL_SHADOW=1 CONTRACTKV_PSTP_REGISTRY="$registry"
    export CONTRACTKV_PHASE16R_EVENT_LOG="$events" CONTRACTKV_PREFIX_METRICS=1
    export CONTRACTKV_PREFIX_INITIAL_ONLY=1 CONTRACTKV_PREFIX_METRICS_LOG="$metrics"
    export CONTRACTKV_POLICY_HASH="$POLICY_HASH" CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000
    export CONTRACTKV_MAX_DEGRADATION=1000000000 EXTRA_VLLM_ARGS="--enable-prefix-caching"
    cleanup_cell(){ bash scripts/stop_vllm_server.sh --pid-path "$pid" --port "$port" || true; }
    trap cleanup_cell EXIT
    bash scripts/run_vllm_server.sh --phase "phase20d-$name" --model-path "$MODEL_PATH" --served-model-name llama31-8b \
      --port "$port" --gpu-ids "$gpu" --tensor-parallel-size 1 --dtype float16 --max-model-len 8192 \
      --max-num-seqs 2 --gpu-memory-utilization .88 --log-path "$log" --pid-path "$pid"
    if [[ "$mode" == "two-tier" ]]; then
      "$PY" scripts/phase20d_two_tier_live.py --sessions "$SESSIONS" --base-url "http://127.0.0.1:$port/v1" \
        --model llama31-8b --registry "$registry" --event-log "$events" --frozen-policy "$FROZEN" \
        --policy-hash "$POLICY_HASH" --concurrency 2 --turns 10 --max-tokens 96 --tool-slack-ms 3000 \
        --metrics-events "$metrics" --output "$output"
    else
      "$PY" scripts/phase19b_end_to_end_live.py --sessions "$SESSIONS" --base-url "http://127.0.0.1:$port/v1" \
        --model llama31-8b --policy "$mode" --policy-hash "$POLICY_HASH" --load-tier phase20-heldout \
        --concurrency 2 --turns 10 --max-tokens 96 --tool-slack-ms 3000 --metrics-events "$metrics" --output "$output"
    fi
  )
}

run_cell raw-order raw-order 0 8052 & p0=$!
run_cell physical-cache-aware physical-cache-aware 1 8053 & p1=$!
failed=0; wait "$p0" || failed=1; wait "$p1" || failed=1; [[ $failed -eq 0 ]] || exit 31
run_cell tier1-only contractkv-full 0 8054 & p0=$!
run_cell contractkv-two-tier two-tier 1 8055 & p1=$!
failed=0; wait "$p0" || failed=1; wait "$p1" || failed=1; [[ $failed -eq 0 ]] || exit 32

"$PY" scripts/phase20d_summarize_one_shot.py --sessions "$SESSIONS" --tool-slack-ms 3000 \
  --cell "raw-order=$OUT/raw-order.jsonl" --cell "physical-cache-aware=$OUT/physical-cache-aware.jsonl" \
  --cell "tier1-only=$OUT/tier1-only.jsonl" --cell "contractkv-two-tier=$OUT/contractkv-two-tier.jsonl" \
  --summary-output results/cross_model/phase20d_one_shot_summary_v0.csv \
  --quality-output results/cross_model/phase20d_one_shot_official_quality_v0.csv \
  --slo-output results/cross_model/phase20d_one_shot_slo_curve_v0.csv \
  --gate-output results/cross_model/phase20d_one_shot_gate_v0.json
echo PHASE20D_COMPLETE
