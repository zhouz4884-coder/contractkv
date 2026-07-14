#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
SOURCE="${SOURCE_VLLM:-$ROOT/third_party/vllm-contractkv-phase19c}"
PROTOCOL="$ROOT/configs/phase25_deepseek_v2_lite_pair_protocol.json"
BASE="$ROOT/results/cross_model/deepseek_v2_lite_pair"
LOG_BASE="$ROOT/logs/phase25_deepseek_v2_lite_pair"
DEV="$ROOT/results/cross_model/llama_broad_generalization_r3/development_sessions_v0.jsonl"
HELD="$ROOT/results/cross_model/llama_broad_generalization_r3/heldout_sealed_sessions_v0.jsonl"
SPLIT="$ROOT/results/cross_model/llama_broad_generalization_r3/split_commitment_v0.json"
PREFLIGHT="$BASE/preflight_sessions_v0.jsonl"
COMMITMENT="$BASE/protocol_commitment_v0.json"
SCHEDULER="$SOURCE/vllm/v1/core/sched/scheduler.py"
STAGE="${PHASE25_STAGE:-all}"
MODEL_FILTER="${PHASE25_MODEL:-both}"
PORT="${PHASE25_PORT:-8950}"

mkdir -p "$BASE" "$LOG_BASE"
cd "$ROOT"
export PYTHONPATH="$SOURCE:$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export CONTRACTKV_VERIFIER_CODE_COMMIT="phase25-deepseek-pair-frozen-protocol-v1"

model_info() {
  case "$1" in
    chat)
      MODEL_PATH="/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/DeepSeek-V2-Lite-Chat"
      SERVED_MODEL="deepseek-v2-lite-chat"
      ;;
    coder)
      MODEL_PATH="/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/DeepSeek-Coder-V2-Lite-Instruct"
      SERVED_MODEL="deepseek-coder-v2-lite-instruct"
      ;;
    *) echo "Unknown model key: $1" >&2; return 2 ;;
  esac
  MODEL_OUT="$BASE/$1"
  MODEL_LOG="$LOG_BASE/$1"
  MANIFEST="$MODEL_OUT/qualification_manifest_v0.json"
  mkdir -p "$MODEL_OUT" "$MODEL_LOG"
}

selected_models() {
  if [[ "$MODEL_FILTER" == "both" ]]; then echo "chat coder"; else echo "$MODEL_FILTER"; fi
}

remove_hooks() {
  "$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action uninstall >/dev/null 2>&1 || true
  "$PY" scripts/install_vllm_v1_phase17_hook.py --scheduler "$SCHEDULER" --action remove >/dev/null 2>&1 || true
  "$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action remove >/dev/null 2>&1 || true
}

install_main_hooks() {
  remove_hooks
  "$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action install
  "$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action install
  "$PY" -m py_compile "$SCHEDULER"
}

install_fault_hooks() {
  remove_hooks
  "$PY" scripts/install_vllm_v1_phase17_hook.py --scheduler "$SCHEDULER" --action install
  "$PY" -m py_compile "$SCHEDULER"
}

stop_server() {
  local pid=$1
  bash scripts/stop_vllm_server.sh --pid-path "$pid" --port "$PORT" >/dev/null 2>&1 || true
}

start_server() {
  local label=$1 log=$2 pid=$3 extra=$4
  export EXTRA_VLLM_ARGS="$extra"
  bash scripts/run_vllm_server.sh --phase "$label" --model-path "$MODEL_PATH" \
    --served-model-name "$SERVED_MODEL" --port "$PORT" --gpu-ids "0,1" \
    --tensor-parallel-size 2 --dtype bfloat16 --max-model-len 8192 \
    --max-num-seqs 2 --gpu-memory-utilization .90 --log-path "$log" --pid-path "$pid"
}

run_fault_preflight() {
  local key=$1
  model_info "$key"
  local marker="$MODEL_OUT/preflight_fault.complete"
  [[ -f "$marker" ]] && return 0
  local policy="$MODEL_OUT/preflight_frozen_policy_v0.json"
  local registry="$MODEL_OUT/preflight_runtime_registry_v0.json"
  local events="$MODEL_OUT/preflight_fault_events_v0.jsonl"
  local output="$MODEL_OUT/preflight_fault_probe_v0.csv"
  local log="$MODEL_LOG/preflight_fault_server.log" pid="$MODEL_LOG/preflight_fault_server.pid"
  "$PY" scripts/contractkv_frozen_policy.py --output "$policy" --model-id "$SERVED_MODEL" \
    --model-path "$MODEL_PATH" --vllm-version 0.10.2 \
    --thresholds results/hard_systems/phase17_frozen_thresholds_v0.json \
    --calibration-csv results/hard_systems/phase17_calibration_candidate_margins_v2.csv --repo "$ROOT"
  rm -f "$registry" "$events" "$output" "$pid"
  install_fault_hooks
  export CONTRACTKV_PHASE17_REGISTRY="$registry" CONTRACTKV_PHASE16R_EVENT_LOG="$events"
  export CONTRACTKV_PHASE17_DOUBLE_FINALIZE=1
  start_server "phase25-${key}-fault" "$log" "$pid" \
    "--enable-prefix-caching --trust-remote-code --scheduling-policy priority --enable-chunked-prefill --max-num-batched-tokens 1024"
  set +e
  "$PY" scripts/phase17r_qwen8b_integrated_live.py --base-url "http://127.0.0.1:$PORT/v1" \
    --model "$SERVED_MODEL" --model-path "$MODEL_PATH" --policy "$policy" \
    --registry "$registry" --event-log "$events" --output "$output"
  local status=$?
  set -e
  stop_server "$pid"
  unset CONTRACTKV_PHASE17_REGISTRY CONTRACTKV_PHASE16R_EVENT_LOG CONTRACTKV_PHASE17_DOUBLE_FINALIZE
  remove_hooks
  # The legacy probe returns non-zero when a model conservatively rejects one
  # of its Qwen-oriented positive markers.  Compatibility is decided below
  # from the transaction invariants, not from those model-specific labels.
  [[ -s "$output" ]] || return "$status"
  touch "$marker"
}

run_main_cell() {
  local key=$1 partition=$2 label=$3 mode=$4 level=$5 sessions=$6 session_count=$7 policy_hash=$8
  model_info "$key"
  local dir="$MODEL_OUT/$partition" output="$MODEL_OUT/$partition/${label}.jsonl"
  local metrics="$MODEL_OUT/$partition/${label}_metrics.jsonl" marker="$MODEL_OUT/$partition/${label}.complete"
  local log="$MODEL_LOG/${label}_server.log" pid="$MODEL_LOG/${label}_server.pid"
  mkdir -p "$dir"
  if [[ -f "$marker" ]]; then
    "$PY" scripts/phase25_deepseek_pair_analysis.py validate-cell --cell "$output" \
      --sessions "$session_count" --turns 10 >/dev/null
    return 0
  fi
  rm -f "$output" "$metrics" "$pid"
  install_main_hooks
  export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1
  export CONTRACTKV_PREFIX_METRICS_LOG="$metrics" CONTRACTKV_POLICY_HASH="$policy_hash"
  export CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000 CONTRACTKV_MAX_DEGRADATION=1000000000
  start_server "phase25-${key}-${label}" "$log" "$pid" "--enable-prefix-caching --trust-remote-code"
  local command=("$PY" scripts/phase22_llama_broad_live.py --sessions "$sessions"
    --base-url "http://127.0.0.1:$PORT/v1" --model "$SERVED_MODEL" --model-identity "$MODEL_PATH"
    --mode "$mode" --level "$level" --policy-hash "$policy_hash" --load-tier "phase25-${key}-${label}"
    --concurrency 2 --turns 10 --stable-word-limit 1500 --max-tokens 128
    --tool-slack-ms 6000 --slo-ms 1500 --metrics-events "$metrics" --output "$output")
  if [[ "$mode" == "frozen" ]]; then command+=(--qualification-manifest "$MANIFEST"); fi
  set +e
  "${command[@]}"
  local status=$?
  set -e
  stop_server "$pid"
  remove_hooks
  unset CONTRACTKV_PREFIX_METRICS CONTRACTKV_PREFIX_INITIAL_ONLY CONTRACTKV_PREFIX_METRICS_LOG CONTRACTKV_POLICY_HASH
  [[ $status -eq 0 ]] || return "$status"
  "$PY" scripts/phase25_deepseek_pair_analysis.py validate-cell --cell "$output" \
    --sessions "$session_count" --turns 10
  touch "$marker"
}

run_compatibility_preflight() {
  local key=$1
  model_info "$key"
  run_fault_preflight "$key"
  run_main_cell "$key" preflight preflight-L3 level L3 "$PREFLIGHT" 10 "phase25-${key}-preflight-v1"
  "$PY" scripts/phase25_deepseek_pair_analysis.py preflight --protocol "$PROTOCOL" \
    --model-key "$key" --model-config "$MODEL_PATH/config.json" \
    --cell "$MODEL_OUT/preflight/preflight-L3.jsonl" \
    --fault-probe "$MODEL_OUT/preflight_fault_probe_v0.csv" --sessions 10 --turns 10 \
    --output "$MODEL_OUT/preflight_compatibility_v0.json"
  touch "$MODEL_OUT/preflight.complete"
}

run_full_model() {
  local key=$1
  model_info "$key"
  [[ -f "$MODEL_OUT/preflight.complete" ]] || { echo "Preflight gate missing for $key" >&2; return 41; }
  local dev_hash="phase25-${key}-development-ladder-v1"
  run_main_cell "$key" development dev-L0 raw L0 "$DEV" 25 "$dev_hash"
  run_main_cell "$key" development dev-L1 level L1 "$DEV" 25 "$dev_hash"
  run_main_cell "$key" development dev-L2 level L2 "$DEV" 25 "$dev_hash"
  run_main_cell "$key" development dev-L3 level L3 "$DEV" 25 "$dev_hash"
  "$PY" scripts/phase22_llama_broad_analysis.py freeze --sessions "$DEV" \
    --cell "L0=$MODEL_OUT/development/dev-L0.jsonl" --cell "L1=$MODEL_OUT/development/dev-L1.jsonl" \
    --cell "L2=$MODEL_OUT/development/dev-L2.jsonl" --cell "L3=$MODEL_OUT/development/dev-L3.jsonl" \
    --model-identity "$MODEL_PATH" --minimum-development-sessions 5 --minimum-admitted-coverage .5 \
    --max-tokens 128 --stable-word-limit 1500 --split-commitment "$SPLIT" \
    --development-summary "$MODEL_OUT/development_layout_summary_v0.csv" \
    --quality-output "$MODEL_OUT/development_quality_v0.csv" --manifest "$MANIFEST"
  local hash
  hash=$("$PY" -c "import json;print(json.load(open('$MANIFEST'))['qualification_hash'])")
  for repeat in 1 2 3; do
    if (( repeat % 2 == 1 )); then
      run_main_cell "$key" "repeat$repeat" "r${repeat}-raw" raw L0 "$HELD" 50 "$hash"
      run_main_cell "$key" "repeat$repeat" "r${repeat}-contract" frozen L0 "$HELD" 50 "$hash"
    else
      run_main_cell "$key" "repeat$repeat" "r${repeat}-contract" frozen L0 "$HELD" 50 "$hash"
      run_main_cell "$key" "repeat$repeat" "r${repeat}-raw" raw L0 "$HELD" 50 "$hash"
    fi
  done
  local pairs=()
  for repeat in 1 2 3; do
    pairs+=(--pair "$repeat,$MODEL_OUT/repeat$repeat/r${repeat}-raw.jsonl,$MODEL_OUT/repeat$repeat/r${repeat}-contract.jsonl")
  done
  "$PY" scripts/phase22_llama_broad_analysis.py heldout --sessions "$HELD" --manifest "$MANIFEST" \
    "${pairs[@]}" --slo-ms 1500 --raw-summary "$MODEL_OUT/heldout_scope_repeats_v0.csv" \
    --aggregate-summary "$MODEL_OUT/heldout_scope_aggregate_v0.csv" \
    --quality-output "$MODEL_OUT/heldout_quality_v0.csv" \
    --level-output "$MODEL_OUT/heldout_level_selection_v0.csv" --gate-output "$MODEL_OUT/heldout_gate_v0.json"
  touch "$MODEL_OUT/full.complete"
}

trap remove_hooks EXIT
"$PY" scripts/phase25_prepare_deepseek_pair.py --protocol "$PROTOCOL" --development "$DEV" \
  --heldout "$HELD" --preflight-output "$PREFLIGHT" --commitment-output "$COMMITMENT"

if [[ "$STAGE" == "preflight" || "$STAGE" == "all" ]]; then
  for key in $(selected_models); do run_compatibility_preflight "$key"; done
fi
if [[ "$STAGE" == "full" || "$STAGE" == "all" ]]; then
  for key in $(selected_models); do run_full_model "$key"; done
fi
if [[ -f "$BASE/chat/full.complete" && -f "$BASE/coder/full.complete" ]]; then
  set +e
  "$PY" scripts/phase25_deepseek_pair_analysis.py summarize --protocol "$PROTOCOL" \
    --chat-dir "$BASE/chat" --coder-dir "$BASE/coder" \
    --summary-output "$BASE/pair_summary_v0.csv" --family-output "$BASE/family_summary_v0.csv" \
    --gate-output "$BASE/pair_gate_v0.json"
  PAIR_STATUS=$?
  set -e
  echo "phase25_pair_gate_status=$PAIR_STATUS"
fi
remove_hooks
trap - EXIT
echo PHASE25_DEEPSEEK_PAIR_COMPLETE
