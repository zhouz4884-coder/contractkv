#!/usr/bin/env bash
# Fresh-process TSC open-loop cells with isolated compile caches.
set -euo pipefail

ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
SOURCE="${VLLM_SOURCE:-$ROOT/third_party/vllm-contractkv-phase19c}"
SCHEDULER="$SOURCE/vllm/v1/core/sched/scheduler.py"
SESSIONS="$ROOT/results/tsc_service/tsc_service_sessions_v0.jsonl"
ARRIVALS="$ROOT/results/tsc_service/tsc_service_arrivals_v0.jsonl"
FAMILY_POLICY="$ROOT/configs/tsc_frozen_family_policy.json"
OUT="$ROOT/results/tsc_service/open_loop_cells"
LOG="$ROOT/logs/tsc_service/open_loop"
PROFILE="${PROFILE:-pilot}"
QWEN_BASELINE_RPS="${QWEN_BASELINE_RPS:-2.0}"
MISTRAL_BASELINE_RPS="${MISTRAL_BASELINE_RPS:-2.0}"
mkdir -p "$OUT" "$LOG" "$ROOT/cache/tsc-service"
cd "$ROOT"
export PYTHONPATH="$SOURCE:$ROOT${PYTHONPATH:+:$PYTHONPATH}"
MAIN_BASHPID=$BASHPID
export VLLM_STARTUP_POLLS="${VLLM_STARTUP_POLLS:-360}"

"$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action install
"$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action install
cleanup_hooks() {
  [[ $BASHPID == "$MAIN_BASHPID" ]] || return 0
  "$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action uninstall >/dev/null 2>&1 || true
  "$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action remove >/dev/null 2>&1 || true
}
trap cleanup_hooks EXIT

run_cell() {
  local label=$1 model_path=$2 served=$3 gpu=$4 port=$5 repeat=$6 policy=$7 fraction=$8 mode=${9:-poisson} max_requests=${10:-0}
  local rate
  if [[ "$label" == "qwen" ]]; then
    rate=$("$PY" -c "print(float('$QWEN_BASELINE_RPS')*float('$fraction'))")
  else
    rate=$("$PY" -c "print(float('$MISTRAL_BASELINE_RPS')*float('$fraction'))")
  fi
  local tag="${label}_r${repeat}_${policy}_f${fraction//./p}_${mode}"
  local cell="tsc-open-${tag}" dir="$OUT/$tag"
  local raw="$dir/raw.jsonl" registration="$dir/registration.jsonl" summary="$dir/summary.jsonl"
  local metrics="$dir/metrics.jsonl" server_log="$LOG/${tag}_server.log" pid="$dir/server.pid"
  local monitor="$dir/gpu_monitor.csv" monitor_pid="$dir/gpu_monitor.pid"
  if [[ -s "$summary" ]]; then
    local expected=1125
    [[ "$max_requests" != "0" ]] && expected="$max_requests"
    local count
    count=$(wc -l < "$raw" 2>/dev/null || echo 0)
    if [[ "$count" == "$expected" && -s "$summary" \
        && $(grep -c '"experiment_version": "tsc-service-v1"' "$summary") -gt 0 ]]; then
      echo "SKIP complete $cell"; return
    fi
  fi
  rm -rf -- "$dir"; mkdir -p "$dir"
  export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1
  export CONTRACTKV_PREFIX_CONCURRENT_SNAPSHOTS=1 CONTRACTKV_PREFIX_METRICS_LOG="$metrics"
  export CONTRACTKV_POLICY_HASH="tsc-service-${label}-frozen-v0"
  export CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000 CONTRACTKV_MAX_DEGRADATION=1000000000
  export EXTRA_VLLM_ARGS="--enable-prefix-caching"
  cleanup_cell() {
    if [[ -f "$monitor_pid" ]]; then kill "$(cat "$monitor_pid")" 2>/dev/null || true; rm -f "$monitor_pid"; fi
    bash scripts/stop_vllm_server.sh --pid-path "$pid" --port "$port" || true
  }
  trap cleanup_cell RETURN
  VLLM_CACHE_ROOT="$ROOT/cache/tsc-service/$tag/vllm" \
  TRITON_CACHE_DIR="$ROOT/cache/tsc-service/$tag/triton" \
  bash scripts/run_vllm_server.sh --phase "$cell" --model-path "$model_path" --served-model-name "$served" \
    --port "$port" --gpu-ids "$gpu" --tensor-parallel-size 1 --dtype float16 \
    --max-model-len 8192 --max-num-seqs 8 --gpu-memory-utilization .88 \
    --log-path "$server_log" --pid-path "$pid"
  (
    echo "timestamp,index,memory.used,memory.total,utilization.gpu,utilization.memory"
    while true; do
      nvidia-smi --query-gpu=timestamp,index,memory.used,memory.total,utilization.gpu,utilization.memory --format=csv,noheader,nounits | sed -n "$((gpu+1))p"
      sleep .5
    done
  ) > "$monitor" & echo $! > "$monitor_pid"
  "$PY" scripts/tsc_open_loop_service.py --sessions "$SESSIONS" --arrivals "$ARRIVALS" \
    --family-policy "$FAMILY_POLICY" --tokenizer "$model_path" --model-identity "$([[ "$label" == qwen ]] && echo Qwen3-8B || echo Mistral-7B-Instruct-v0.3)" \
    --policy "$policy" --arrival-rate-rps "$rate" --arrival-mode "$mode" \
    --base-url "http://127.0.0.1:$port/v1" --model "$served" --cell-id "$cell" \
    --metrics-events "$metrics" --raw-output "$raw" --registration-output "$registration" --summary-output "$summary" \
    --max-requests "$max_requests" --policy-hash "tsc-service-${label}-frozen-v0" --load-tier "$tag"
  cleanup_cell; trap - RETURN
}

pilot_model() {
  local label=$1 model=$2 served=$3 gpu=$4 base_port=$5
  local index=0
  for rate_fraction in .25 .5 1 2 4; do
    index=$((index+1))
    run_cell "$label" "$model" "$served" "$gpu" $((base_port+index)) 0 D0-native-apc "$rate_fraction" poisson 200
  done
}

full_model() {
  local label=$1 model=$2 served=$3 gpu=$4 base_port=$5 key_only=${6:-0} worker_mod=${7:-1} worker_rem=${8:-0}
  local fractions=".6 .8 1.0 1.2" policies="D0-native-apc D1-frozen-safe D2-full-contractkv"
  [[ "$key_only" == "1" ]] && { fractions=".8 1.0 1.2"; policies="D0-native-apc D2-full-contractkv"; }
  local index=0
  for repeat in 1 2 3; do
    case "$repeat" in
      1) order="$policies" ;;
      2) order="D1-frozen-safe D2-full-contractkv D0-native-apc" ;;
      *) order="D2-full-contractkv D0-native-apc D1-frozen-safe" ;;
    esac
    for fraction in $fractions; do
      for policy in $order; do
        [[ " $policies " == *" $policy "* ]] || continue
        index=$((index+1))
        (( index % worker_mod == worker_rem )) || continue
        run_cell "$label" "$model" "$served" "$gpu" $((base_port + index % 50)) "$repeat" "$policy" "$fraction" poisson 0
      done
    done
    for policy in D0-native-apc D2-full-contractkv; do
      [[ " $policies " == *" $policy "* ]] || continue
      index=$((index+1))
      (( index % worker_mod == worker_rem )) || continue
      run_cell "$label" "$model" "$served" "$gpu" $((base_port + index % 50)) "$repeat" "$policy" .8 onoff 0
    done
  done
}

QWEN_MODEL=/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-8B
MISTRAL_MODEL=/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Mistral-7B-Instruct-v0.3
case "$PROFILE" in
  pilot)
    pilot_model qwen "$QWEN_MODEL" qwen3-8b 0 8300 & p0=$!
    pilot_model mistral "$MISTRAL_MODEL" mistral7b 1 8400 & p1=$!
    failed=0; wait "$p0" || failed=1; wait "$p1" || failed=1; exit "$failed"
    ;;
  full)
    # Balance the 42 Qwen and 24 Mistral cells across both GPUs. Each cell is
    # still single-GPU and fresh-process; only inter-cell scheduling changes.
    full_model qwen "$QWEN_MODEL" qwen3-8b 0 8300 0 2 0 & p0=$!
    full_model qwen "$QWEN_MODEL" qwen3-8b 1 8400 0 2 1 & p1=$!
    failed=0; wait "$p0" || failed=1; wait "$p1" || failed=1; [[ $failed -eq 0 ]] || exit "$failed"
    full_model mistral "$MISTRAL_MODEL" mistral7b 0 8500 1 2 0 & p0=$!
    full_model mistral "$MISTRAL_MODEL" mistral7b 1 8600 1 2 1 & p1=$!
    wait "$p0" || failed=1; wait "$p1" || failed=1; exit "$failed"
    ;;
  qwen-full) full_model qwen "$QWEN_MODEL" qwen3-8b 0 8300 0 ;;
  mistral-key) full_model mistral "$MISTRAL_MODEL" mistral7b 1 8400 1 ;;
  *) echo "unknown PROFILE=$PROFILE" >&2; exit 64 ;;
esac
