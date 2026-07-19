#!/usr/bin/env bash
# Prospective service-template locality sweep, separate from natural mixed trace.
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
SOURCE="${VLLM_SOURCE:-$ROOT/third_party/vllm-contractkv-phase19c}"
SCHEDULER="$SOURCE/vllm/v1/core/sched/scheduler.py"
ARRIVALS="$ROOT/results/tsc_service/tsc_service_arrivals_v0.jsonl"
FAMILY_POLICY="$ROOT/configs/tsc_frozen_family_policy.json"
OUT="$ROOT/results/tsc_service/locality_cells"; LOG="$ROOT/logs/tsc_service/locality"
PROFILE="${PROFILE:-full}"
mkdir -p "$OUT" "$LOG" "$ROOT/cache/tsc-locality"; cd "$ROOT"
export PYTHONPATH="$SOURCE:$ROOT${PYTHONPATH:+:$PYTHONPATH}" VLLM_STARTUP_POLLS="${VLLM_STARTUP_POLLS:-360}"
MAIN_BASHPID=$BASHPID
"$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action install
"$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action install
cleanup_hooks(){
  [[ $BASHPID == "$MAIN_BASHPID" ]] || return 0
  "$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action uninstall >/dev/null 2>&1 || true
  "$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action remove >/dev/null 2>&1 || true
}
trap cleanup_hooks EXIT

run_cell(){
  local label=$1 model_path=$2 served=$3 identity=$4 level=$5 repeat=$6 policy=$7 policy_label=$8
  local scope_mode=$9 fraction=${10} gpu=${11} port=${12}
  local sessions="$ROOT/results/tsc_service/tsc_service_sessions_locality_g${level}_v0.jsonl"
  local tag="${label}_g${level}_r${repeat}_${policy_label}_f${fraction//./p}"
  local dir="$OUT/$tag"
  local raw="$dir/raw.jsonl" summary="$dir/summary.jsonl" metrics="$dir/metrics.jsonl" registration="$dir/registration.jsonl"
  local pid="$dir/server.pid"
  [[ -s "$summary" && $(wc -l < "$raw" 2>/dev/null || echo 0) -eq 1125 \
      && $(grep -c '"experiment_version": "tsc-service-v1"' "$summary") -gt 0 ]] \
      && { echo "SKIP $tag"; return; }
  rm -rf -- "$dir"; mkdir -p "$dir"
  export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1 CONTRACTKV_PREFIX_CONCURRENT_SNAPSHOTS=1 CONTRACTKV_PREFIX_METRICS_LOG="$metrics"
  export CONTRACTKV_POLICY_HASH="tsc-locality-$label-g$level-v0" CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000 CONTRACTKV_MAX_DEGRADATION=1000000000
  export EXTRA_VLLM_ARGS="--enable-prefix-caching"
  cleanup_cell(){ bash scripts/stop_vllm_server.sh --pid-path "$pid" --port "$port" || true; }
  trap cleanup_cell RETURN
  VLLM_CACHE_ROOT="$ROOT/cache/tsc-locality/$tag/vllm" TRITON_CACHE_DIR="$ROOT/cache/tsc-locality/$tag/triton" \
  bash scripts/run_vllm_server.sh --phase "tsc-locality-$tag" --model-path "$model_path" --served-model-name "$served" \
    --port "$port" --gpu-ids "$gpu" --tensor-parallel-size 1 --dtype float16 --max-model-len 8192 --max-num-seqs 8 \
    --gpu-memory-utilization .88 --log-path "$LOG/${tag}_server.log" --pid-path "$pid"
  "$PY" scripts/tsc_open_loop_service.py --sessions "$sessions" --arrivals "$ARRIVALS" --family-policy "$FAMILY_POLICY" \
    --tokenizer "$model_path" --model-identity "$identity" --policy "$policy" --policy-label "$policy_label" --arrival-rate-rps "$fraction" \
    --base-url "http://127.0.0.1:$port/v1" --model "$served" --cell-id "tsc-locality-$tag" \
    --metrics-events "$metrics" --raw-output "$raw" --registration-output "$registration" --summary-output "$summary" \
    --policy-hash "tsc-locality-$label-g$level-v0" --load-tier "$tag" \
    --certificate-scope-mode "$scope_mode"
  cleanup_cell; trap - RETURN
}

worker(){
  local gpu=$1 base_port=$2 mod=$3 rem=$4 index=0
  # Qwen: cohort-5 diagnosis at 80%, and full family-shared load curve.
  for repeat in 1 2 3; do
    for level in 1 5 25; do
      fractions=".8"; [[ "$level" == 25 ]] && fractions=".2 .4 .6 .8 1.0 1.2 1.4 2.0 4.0 6.0 8.0"
      policy_specs="D0-native-apc:D0-native-apc:service_template D2-full-contractkv:D2-template-contractkv:service_template"
      [[ "$level" == 25 ]] && policy_specs="$policy_specs D1-frozen-safe:D1-frozen-safe:service_template"
      for fraction in $fractions; do
        for policy_spec in $policy_specs; do
          IFS=: read -r policy policy_label scope_mode <<< "$policy_spec"
          index=$((index+1)); (( index % mod == rem )) || continue
          run_cell qwen /media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-8B qwen3-8b Qwen3-8B "$level" "$repeat" "$policy" "$policy_label" "$scope_mode" "$fraction" "$gpu" $((base_port+index%50))
        done
      done
    done
  done
  # Mistral replication: strongest shared scope at low/mid/high load.
  for repeat in 1 2 3; do
    for fraction in .8 1.0 1.2; do
      for policy_spec in 'D0-native-apc:D0-native-apc:service_template' 'D2-full-contractkv:D2-template-contractkv:service_template'; do
        IFS=: read -r policy policy_label scope_mode <<< "$policy_spec"
        index=$((index+1)); (( index % mod == rem )) || continue
        run_cell mistral /media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Mistral-7B-Instruct-v0.3 mistral7b Mistral-7B-Instruct-v0.3 25 "$repeat" "$policy" "$policy_label" "$scope_mode" "$fraction" "$gpu" $((base_port+index%50))
      done
    done
  done
}

case "$PROFILE" in
  template-pilot)
    run_cell qwen /media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-8B qwen3-8b Qwen3-8B 25 0 D2-full-contractkv D2-template-contractkv service_template .8 0 9303
    ;;
  pilot)
    run_cell qwen /media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-8B qwen3-8b Qwen3-8B 25 0 D0-native-apc D0-native-apc service_template .8 0 9301 & p0=$!
    run_cell qwen /media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-8B qwen3-8b Qwen3-8B 25 0 D2-full-contractkv D2-template-contractkv service_template .8 1 9401 & p1=$!
    failed=0; wait "$p0" || failed=1; wait "$p1" || failed=1; [[ $failed -eq 0 ]] || exit "$failed"
    run_cell qwen /media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-8B qwen3-8b Qwen3-8B 25 0 D1-frozen-safe D1-frozen-safe service_template .8 0 9302 & p0=$!
    run_cell qwen /media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-8B qwen3-8b Qwen3-8B 25 0 D2-full-contractkv D2-session-contractkv qualified_session .8 1 9402 & p1=$!
    failed=0; wait "$p0" || failed=1; wait "$p1" || failed=1
    [[ $failed -eq 0 ]] && "$PY" scripts/validate_tsc_locality_pilot.py
    exit "$failed"
    ;;
  full)
    "$PY" scripts/validate_tsc_locality_pilot.py
    worker 0 9300 2 0 & p0=$!
    worker 1 9400 2 1 & p1=$!
    failed=0; wait "$p0" || failed=1; wait "$p1" || failed=1
    exit "$failed"
    ;;
  *) echo "unknown PROFILE=$PROFILE" >&2; exit 64 ;;
esac
