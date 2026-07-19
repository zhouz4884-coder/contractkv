#!/usr/bin/env bash
# Paired fresh-process real-task audit for service-template certificate fan-out.
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
SOURCE="${VLLM_SOURCE:-$ROOT/third_party/vllm-contractkv-phase19c}"
SCHEDULER="$SOURCE/vllm/v1/core/sched/scheduler.py"
MODEL_PATH="/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-8B"
SESSIONS="$ROOT/results/tsc_service/quality/tsc_service_quality_sessions_v0.jsonl"
PROTOCOL="$ROOT/configs/tsc_service_quality_protocol.json"
OUT="$ROOT/results/tsc_service/quality/cells"
LOG="$ROOT/logs/tsc_service/quality"
mkdir -p "$OUT" "$LOG" "$ROOT/cache/tsc-quality"; cd "$ROOT"
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
  local repeat=$1 policy=$2 gpu=$3 port=$4
  local tag="qwen_r${repeat}_${policy}" dir="$OUT/qwen_r${repeat}_${policy}"
  local raw="$dir/raw.jsonl" summary="$dir/summary.jsonl" registration="$dir/registration.jsonl"
  local metrics="$dir/metrics.jsonl" pid="$dir/server.pid"
  [[ -s "$summary" && $(wc -l < "$raw" 2>/dev/null || echo 0) -eq 450 ]] && { echo "SKIP $tag"; return; }
  rm -rf -- "$dir"; mkdir -p "$dir"
  export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1 CONTRACTKV_PREFIX_CONCURRENT_SNAPSHOTS=1
  export CONTRACTKV_PREFIX_METRICS_LOG="$metrics" CONTRACTKV_POLICY_HASH="tsc-quality-qwen-v0"
  export CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000 CONTRACTKV_MAX_DEGRADATION=1000000000
  export EXTRA_VLLM_ARGS="--enable-prefix-caching"
  cleanup_cell(){ bash scripts/stop_vllm_server.sh --pid-path "$pid" --port "$port" || true; }
  trap cleanup_cell RETURN
  VLLM_CACHE_ROOT="$ROOT/cache/tsc-quality/$tag/vllm" TRITON_CACHE_DIR="$ROOT/cache/tsc-quality/$tag/triton" \
  bash scripts/run_vllm_server.sh --phase "tsc-quality-$tag" --model-path "$MODEL_PATH" --served-model-name qwen3-8b \
    --port "$port" --gpu-ids "$gpu" --tensor-parallel-size 1 --dtype float16 --max-model-len 8192 --max-num-seqs 4 \
    --gpu-memory-utilization .88 --log-path "$LOG/${tag}_server.log" --pid-path "$pid"
  "$PY" scripts/tsc_service_template_quality_live.py --sessions "$SESSIONS" --protocol "$PROTOCOL" \
    --tokenizer "$MODEL_PATH" --model-identity Qwen3-8B --policy "$policy" --base-url "http://127.0.0.1:$port/v1" \
    --model qwen3-8b --cell-id "tsc-quality-$tag" --repeat "$repeat" --metrics-events "$metrics" \
    --raw-output "$raw" --registration-output "$registration" --summary-output "$summary" --concurrency 2
  cleanup_cell; trap - RETURN
}

for repeat in 1 2 3; do
  run_cell "$repeat" D0-native-apc 0 $((9500+repeat)) & p0=$!
  run_cell "$repeat" D2-template-contractkv 1 $((9600+repeat)) & p1=$!
  failed=0; wait "$p0" || failed=1; wait "$p1" || failed=1
  [[ $failed -eq 0 ]] || exit "$failed"
done
