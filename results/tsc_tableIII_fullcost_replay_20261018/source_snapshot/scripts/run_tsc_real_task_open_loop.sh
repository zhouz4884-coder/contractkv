#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
SOURCE="${VLLM_SOURCE:-$ROOT/third_party/vllm-contractkv-phase19c}"
MODEL="/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-8B"
SESSIONS="$ROOT/results/tsc_service/quality/tsc_service_quality_sessions_v0.jsonl"
PROTOCOL="$ROOT/configs/tsc_service_quality_protocol.json"
OUT="$ROOT/results/tsc_closure/real_task_open_loop_v1"; LOG="$ROOT/logs/tsc_closure/real_task_open_loop_v1"
SCHEDULER="$SOURCE/vllm/v1/core/sched/scheduler.py"
CELLS="${CELLS:-D0-native-apc:1 D1-frozen-safe:1 D2-template-contractkv:1 D2-template-contractkv:2 D1-frozen-safe:2 D0-native-apc:2 D0-native-apc:3 D1-frozen-safe:3 D2-template-contractkv:3 D2-template-contractkv:4 D1-frozen-safe:4 D0-native-apc:4 D0-native-apc:5 D1-frozen-safe:5 D2-template-contractkv:5}"
mkdir -p "$OUT" "$LOG" "$ROOT/cache/tsc-real-task-v1"; cd "$ROOT"
export PYTHONPATH="$SOURCE:$ROOT${PYTHONPATH:+:$PYTHONPATH}"
"$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action install
"$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action install
cleanup_hooks(){
  "$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action uninstall >/dev/null 2>&1 || true
  "$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action remove >/dev/null 2>&1 || true
}
trap cleanup_hooks EXIT

complete(){
  [[ -s "$1" && -s "$2" ]] || return 1
  "$PY" -c 'import json,sys; raw=[json.loads(x) for x in open(sys.argv[1]) if x.strip()]; summary=[json.loads(x) for x in open(sys.argv[2]) if x.strip()]; raise SystemExit(0 if len(raw)==450 and len(summary)==4 and all(x.get("completed_requests")==450 for x in summary) else 1)' "$1" "$2"
}

run_cell(){
  local policy=$1 repeat=$2 gpu=$3 port=$4
  local tag="qwen-r${repeat}-${policy}"
  local dir="$OUT/$tag"; mkdir -p "$dir"
  local raw="$dir/raw.jsonl" registration="$dir/registration.jsonl" summary="$dir/summary.jsonl"
  local metrics="$dir/metrics.jsonl" pid="$dir/server.pid" server_log="$LOG/$tag.log"
  complete "$raw" "$summary" && { echo "SKIP_COMPLETE $tag"; return; }
  rm -f "$raw" "$registration" "$summary" "$metrics" "$pid"
  (
    export CUDA_VISIBLE_DEVICES="$gpu" CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1
    export CONTRACTKV_PREFIX_CONCURRENT_SNAPSHOTS=1 CONTRACTKV_PREFIX_METRICS_LOG="$metrics"
    export CONTRACTKV_POLICY_HASH="tsc-real-task-v1" CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000
    export CONTRACTKV_MAX_DEGRADATION=1000000000 EXTRA_VLLM_ARGS="--enable-prefix-caching"
    cleanup(){ bash scripts/stop_vllm_server.sh --pid-path "$pid" --port "$port" || true; }
    trap cleanup EXIT
    VLLM_CACHE_ROOT="$ROOT/cache/tsc-real-task-v1/$tag/vllm" TRITON_CACHE_DIR="$ROOT/cache/tsc-real-task-v1/$tag/triton" \
    bash scripts/run_vllm_server.sh --phase "$tag" --model-path "$MODEL" --served-model-name qwen3-8b \
      --port "$port" --gpu-ids "$gpu" --tensor-parallel-size 1 --dtype float16 --max-model-len 8192 \
      --max-num-seqs 8 --gpu-memory-utilization .88 --log-path "$server_log" --pid-path "$pid"
    "$PY" scripts/tsc_real_task_open_loop.py --sessions "$SESSIONS" --protocol "$PROTOCOL" \
      --tokenizer "$MODEL" --model-identity Qwen3-8B --policy "$policy" --repeat "$repeat" \
      --base-url "http://127.0.0.1:$port/v1" --model qwen3-8b --cell-id "$tag" --arrival-rate-rps 1.6 \
      --seed $((20260722 + repeat)) --metrics-events "$metrics" --raw-output "$raw" \
      --registration-output "$registration" --summary-output "$summary"
  )
}

items=($CELLS); i=0
while (( i < ${#items[@]} )); do
  left="${items[$i]}"; right="${items[$((i+1))]:-}"
  IFS=: read -r lp lr <<<"$left"; run_cell "$lp" "$lr" 0 $((9100+i)) & p0=$!
  if [[ -n "$right" ]]; then
    IFS=: read -r rp rr <<<"$right"; run_cell "$rp" "$rr" 1 $((9300+i)) & p1=$!
    wait "$p0"; wait "$p1"
  else wait "$p0"; fi
  i=$((i+2))
done
echo TSC_REAL_TASK_OPEN_LOOP_COMPLETE
