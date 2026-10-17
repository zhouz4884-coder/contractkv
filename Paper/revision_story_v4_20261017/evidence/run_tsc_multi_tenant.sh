#!/usr/bin/env bash
# Staged fresh-process tenant sharing/isolation evaluation on Qwen3-8B.
set -euo pipefail

ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
SOURCE="${VLLM_SOURCE:-$ROOT/third_party/vllm-contractkv-phase19c}"
SCHEDULER="$SOURCE/vllm/v1/core/sched/scheduler.py"
MODEL=/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-8B
OUT="$ROOT/results/tsc_service/multi_tenant_cells"; LOG="$ROOT/logs/tsc_service/multi_tenant"
PROFILE="${PROFILE:-all}"
mkdir -p "$OUT" "$LOG" "$ROOT/cache/tsc-tenant"; cd "$ROOT"
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
  local repeat=$1 policy=$2 tenants=$3 ratio=$4 gpu=$5 port=$6 kind=$7 allow_capacity=${8:-0}
  local tag="${kind}_r${repeat}_${policy}_n${tenants}_s${ratio//./p}"
  local dir="$OUT/$tag"
  local metrics="$dir/metrics.jsonl" raw="$dir/raw.jsonl" summary="$dir/summary.jsonl"
  local registration="$dir/registration.jsonl" pid="$dir/server.pid"
  [[ -s "$summary" && $(wc -l < "$raw" 2>/dev/null || echo 0) -eq $((tenants*9)) \
      && $(grep -c '"experiment_version": "tsc-service-v1"' "$summary") -gt 0 ]] \
      && { echo "SKIP $tag"; return; }
  rm -rf -- "$dir"; mkdir -p "$dir"
  export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1 CONTRACTKV_PREFIX_CONCURRENT_SNAPSHOTS=1
  export CONTRACTKV_PREFIX_METRICS_LOG="$metrics" CONTRACTKV_POLICY_HASH="tsc-tenant-$tag"
  export CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000 CONTRACTKV_MAX_DEGRADATION=1000000000 EXTRA_VLLM_ARGS="--enable-prefix-caching"
  cleanup_cell(){ bash scripts/stop_vllm_server.sh --pid-path "$pid" --port "$port" || true; }
  trap cleanup_cell RETURN
  VLLM_CACHE_ROOT="$ROOT/cache/tsc-tenant/$tag/vllm" TRITON_CACHE_DIR="$ROOT/cache/tsc-tenant/$tag/triton" \
  bash scripts/run_vllm_server.sh --phase "tsc-tenant-$tag" --model-path "$MODEL" --served-model-name qwen3-8b \
    --port "$port" --gpu-ids "$gpu" --tensor-parallel-size 1 --dtype float16 --max-model-len 8192 \
    --max-num-seqs 8 --gpu-memory-utilization .88 --log-path "$LOG/${tag}_server.log" --pid-path "$pid"
  capacity_arg=(); [[ "$allow_capacity" == "1" ]] && capacity_arg=(--allow-capacity-failure)
  "$PY" scripts/tsc_multi_tenant_live.py --policy "$policy" --tenants "$tenants" --sharing-ratio "$ratio" \
    --concurrency 4 --tokenizer "$MODEL" --base-url "http://127.0.0.1:$port/v1" --model qwen3-8b \
    --cell-id "tsc-tenant-$tag" --metrics-events "$metrics" --raw-output "$raw" --summary-output "$summary" \
    --registration-output "$registration" --policy-hash "tsc-tenant-$tag" "${capacity_arg[@]}"
  cleanup_cell; trap - RETURN
}

scan_worker(){
  local kind=$1 tenants=$2 ratios=$3 policies=$4 gpu=$5 base_port=$6 worker_mod=$7 worker_rem=$8 index=0
  for repeat in 1 2 3; do
    case "$repeat" in
      1) order="$policies" ;;
      2) order="D1-frozen-safe D2-full-contractkv D0-native-apc" ;;
      *) order="D2-full-contractkv D0-native-apc D1-frozen-safe" ;;
    esac
    for ratio in $ratios; do
      for policy in $order; do
        [[ " $policies " == *" $policy "* ]] || continue
        index=$((index+1)); (( index % worker_mod == worker_rem )) || continue
        run_cell "$repeat" "$policy" "$tenants" "$ratio" "$gpu" $((base_port+index%50)) "$kind"
      done
    done
  done
}

stage_gate(){
  "$PY" - <<'PY'
import glob,json
paths=glob.glob('results/tsc_service/multi_tenant_cells/stageA_*/summary.jsonl')
assert len(paths)==18, len(paths)
for path in paths:
 rows=[json.loads(x) for x in open(path)]; row=next(x for x in rows if x['service_class']=='ALL')
 assert row['completion_rate']==1 and row['quality_sanity_rate']==1
 assert row['unauthorized_cross_tenant_reuse']==0 and row['dynamic_suffix_reuse_blocks']==0
 assert row['scope_invalid_admissions']==0 and row['allowed_refcount_match_rate']==1
print('TSC_TENANT_STAGE_A_PASS')
PY
}

run_stage_a(){
  local policies="D0-native-apc D1-frozen-safe D2-full-contractkv"
  scan_worker stageA 10 "0 .75" "$policies" 0 8500 2 0 & p0=$!
  scan_worker stageA 10 "0 .75" "$policies" 1 8600 2 1 & p1=$!
  failed=0; wait "$p0" || failed=1; wait "$p1" || failed=1; [[ $failed -eq 0 ]] || exit "$failed"
  stage_gate
}

run_stage_b(){
  local policies="D0-native-apc D2-full-contractkv"
  scan_worker stageB 20 "0 .5 1.0" "$policies" 0 8700 2 0 & p0=$!
  scan_worker stageB 20 "0 .5 1.0" "$policies" 1 8800 2 1 & p1=$!
  failed=0; wait "$p0" || failed=1; wait "$p1" || failed=1
  [[ $failed -eq 0 ]]
}

run_stage_c(){
  # Full-strength sharing curve at 40 active tenants.
  local policies="D0-native-apc D2-full-contractkv"
  scan_worker stageC 40 "0 .25 .5 .75 1.0" "$policies" 0 8900 2 0 & p0=$!
  scan_worker stageC 40 "0 .25 .5 .75 1.0" "$policies" 1 9000 2 1 & p1=$!
  failed=0; wait "$p0" || failed=1; wait "$p1" || failed=1
  [[ $failed -eq 0 ]]
}

density_worker(){
  local gpu=$1 base_port=$2 worker_mod=$3 worker_rem=$4 index=0
  for repeat in 1 2 3; do
    if (( repeat % 2 == 1 )); then order="D0-native-apc D2-full-contractkv"; else order="D2-full-contractkv D0-native-apc"; fi
    for tenants in 10 20 30 40 60 80; do
      for policy in $order; do
        index=$((index+1)); (( index % worker_mod == worker_rem )) || continue
        run_cell "$repeat" "$policy" "$tenants" 1.0 "$gpu" $((base_port+index%50)) density 1
      done
    done
  done
}

run_density(){
  density_worker 0 9100 2 0 & p0=$!
  density_worker 1 9200 2 1 & p1=$!
  failed=0; wait "$p0" || failed=1; wait "$p1" || failed=1
  [[ $failed -eq 0 ]]
}

case "$PROFILE" in
  all) run_stage_a; run_stage_b; run_stage_c; run_density ;;
  stageA) run_stage_a ;;
  stageB) stage_gate; run_stage_b ;;
  stageC) stage_gate; run_stage_c ;;
  density) stage_gate; run_density ;;
  *) echo "unknown PROFILE=$PROFILE" >&2; exit 64 ;;
esac
