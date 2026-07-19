#!/usr/bin/env bash
# Active-template working-set x arrival-distribution live vLLM sweep.
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
SOURCE="${VLLM_SOURCE:-$ROOT/third_party/vllm-contractkv-phase19c}"
SCHEDULER="$SOURCE/vllm/v1/core/sched/scheduler.py"; MODEL=/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-8B
OUT="$ROOT/results/tsc_service/residency_cells"; LOG="$ROOT/logs/tsc_service/residency"
mkdir -p "$OUT" "$LOG" "$ROOT/cache/tsc-residency"; cd "$ROOT"
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
  local templates=$1 distribution=$2 repeat=$3 policy=$4 policy_label=$5 gpu=$6 port=$7
  local tag="t${templates}_${distribution}_r${repeat}_${policy_label}"
  local dir="$OUT/$tag"
  local sessions="$ROOT/results/tsc_service/tsc_service_sessions_templates_t${templates}_v0.jsonl"
  local arrivals="$ROOT/results/tsc_service/tsc_residency_arrivals_t${templates}_${distribution}_v0.jsonl"
  [[ -s "$dir/summary.jsonl" && $(wc -l < "$dir/raw.jsonl" 2>/dev/null || echo 0) -eq 1125 \
      && $(grep -c '"experiment_version": "tsc-service-v1"' "$dir/summary.jsonl") -gt 0 ]] \
      && { echo "SKIP $tag"; return; }
  rm -rf -- "$dir"; mkdir -p "$dir"
  local hash="tsc-residency-t${templates}-v0" pid="$dir/server.pid"
  export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1 CONTRACTKV_PREFIX_CONCURRENT_SNAPSHOTS=1 CONTRACTKV_PREFIX_METRICS_LOG="$dir/metrics.jsonl"
  export CONTRACTKV_POLICY_HASH="$hash" CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000 CONTRACTKV_MAX_DEGRADATION=1000000000 EXTRA_VLLM_ARGS="--enable-prefix-caching"
  cleanup_cell(){ bash scripts/stop_vllm_server.sh --pid-path "$pid" --port "$port" || true; }; trap cleanup_cell RETURN
  VLLM_CACHE_ROOT="$ROOT/cache/tsc-residency/$tag/vllm" TRITON_CACHE_DIR="$ROOT/cache/tsc-residency/$tag/triton" \
  bash scripts/run_vllm_server.sh --phase "tsc-residency-$tag" --model-path "$MODEL" --served-model-name qwen3-8b --port "$port" --gpu-ids "$gpu" --tensor-parallel-size 1 --dtype float16 --max-model-len 8192 --max-num-seqs 8 --gpu-memory-utilization .88 --log-path "$LOG/${tag}_server.log" --pid-path "$pid"
  "$PY" scripts/tsc_open_loop_service.py --sessions "$sessions" --arrivals "$arrivals" --family-policy configs/tsc_frozen_family_policy.json --tokenizer "$MODEL" --model-identity Qwen3-8B --policy "$policy" --policy-label "$policy_label" --arrival-rate-rps 1.0 --base-url "http://127.0.0.1:$port/v1" --model qwen3-8b --cell-id "tsc-residency-$tag" --metrics-events "$dir/metrics.jsonl" --raw-output "$dir/raw.jsonl" --registration-output "$dir/registration.jsonl" --summary-output "$dir/summary.jsonl" --policy-hash "$hash" --load-tier "$tag" --certificate-scope-mode service_template
  cleanup_cell; trap - RETURN
}

worker(){
  local gpu=$1 base_port=$2 mod=$3 rem=$4 index=0
  for repeat in 1 2 3; do
    for templates in 5 25 50; do
      for distribution in round_robin zipf; do
        for spec in D0-native-apc:D0-native-apc D2-full-contractkv:D2-template-contractkv; do
          IFS=: read -r policy label <<< "$spec"
          index=$((index+1)); (( index % mod == rem )) || continue
          run_cell "$templates" "$distribution" "$repeat" "$policy" "$label" "$gpu" $((base_port+index%50))
        done
      done
    done
  done
}
worker 0 9500 2 0 & p0=$!; worker 1 9600 2 1 & p1=$!
failed=0; wait "$p0" || failed=1; wait "$p1" || failed=1; exit "$failed"
