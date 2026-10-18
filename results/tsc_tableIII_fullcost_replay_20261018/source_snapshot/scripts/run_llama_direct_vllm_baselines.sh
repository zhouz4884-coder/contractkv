#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
MODEL="/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Llama-3.1-8B-Instruct"
SOURCE="${SOURCE_VLLM:-$ROOT/third_party/vllm-contractkv-phase19c}"
SESSIONS="$ROOT/results/cross_model/llama_broad_generalization_r3/heldout_sealed_sessions_v0.jsonl"
MANIFEST="$ROOT/results/cross_model/llama_broad_generalization_r3/llama_broad_qualification_v0.json"
OUT="$ROOT/results/external_baseline/llama_direct_v1"
LOG="$ROOT/logs/external_baseline/llama_direct_v1"
SCHEDULER="$SOURCE/vllm/v1/core/sched/scheduler.py"
CELLS="${CELLS:-raw:4 contract:4 raw:5 contract:5 oracle:1 oracle:2 oracle:3 oracle:4 oracle:5}"
mkdir -p "$OUT" "$LOG"; cd "$ROOT"
export PYTHONPATH="$SOURCE:$ROOT${PYTHONPATH:+:$PYTHONPATH}"

"$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action install
"$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action install
cleanup_hooks() {
  "$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action uninstall >/dev/null 2>&1 || true
  "$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action remove >/dev/null 2>&1 || true
}
trap cleanup_hooks EXIT

complete() {
  local output=$1
  [[ -s "$output" ]] || return 1
  "$PY" -c 'import json,sys; rows=[json.loads(x) for x in open(sys.argv[1]) if x.strip()]; fut=[x for x in rows if x.get("row_type")=="future"]; raise SystemExit(0 if len(fut)==450 and sum(x.get("success") is True for x in fut)==450 else 1)' "$output"
}

run_cell() {
  local mode=$1 repeat=$2 gpu=$3 port=$4
  local tag="llama-r${repeat}-${mode}" output="$OUT/llama-r${repeat}-${mode}.jsonl"
  local metrics="$OUT/llama-r${repeat}-${mode}_metrics.jsonl" pid="$LOG/$tag.pid" log="$LOG/$tag.log"
  complete "$output" && { echo "SKIP_COMPLETE $tag"; return; }
  rm -f "$output" "$metrics" "$pid"
  (
    export CUDA_VISIBLE_DEVICES="$gpu" CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1
    export CONTRACTKV_PREFIX_METRICS_LOG="$metrics" CONTRACTKV_POLICY_HASH="llama-direct-v1"
    export CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000 CONTRACTKV_MAX_DEGRADATION=1000000000
    export EXTRA_VLLM_ARGS="--enable-prefix-caching"
    cleanup_server(){ bash scripts/stop_vllm_server.sh --pid-path "$pid" --port "$port" || true; }
    trap cleanup_server EXIT
    bash scripts/run_vllm_server.sh --phase "$tag" --model-path "$MODEL" --served-model-name llama31-8b \
      --port "$port" --gpu-ids "$gpu" --tensor-parallel-size 1 --dtype float16 \
      --max-model-len 8192 --max-num-seqs 2 --gpu-memory-utilization .88 --log-path "$log" --pid-path "$pid"
    local runner_mode="$mode"
    [[ "$mode" == contract ]] && runner_mode=frozen
    args=(--sessions "$SESSIONS" --base-url "http://127.0.0.1:$port/v1" --model llama31-8b \
      --model-identity "$MODEL" --mode "$runner_mode" --qualification-manifest "$MANIFEST" \
      --policy-hash llama-direct-v1 --load-tier "$tag" --concurrency 2 --turns 10 \
      --stable-word-limit 1500 --stable-pieces 16 --max-tokens 96 --tool-slack-ms 6000 --slo-ms 1500 \
      --metrics-events "$metrics" --output "$output")
    if [[ "$mode" == raw ]]; then
      "$PY" scripts/phase22_llama_broad_live.py --sessions "$SESSIONS" \
        --base-url "http://127.0.0.1:$port/v1" --model llama31-8b --model-identity "$MODEL" --mode raw \
        --policy-hash llama-direct-v1 --load-tier "$tag" --concurrency 2 --turns 10 --stable-word-limit 1500 \
        --stable-pieces 16 --max-tokens 96 --tool-slack-ms 6000 --slo-ms 1500 --metrics-events "$metrics" --output "$output"
    else
      "$PY" scripts/phase22_llama_broad_live.py "${args[@]}"
    fi
  )
}

pending=($CELLS)
index=0
while (( index < ${#pending[@]} )); do
  left="${pending[$index]}"; right="${pending[$((index+1))]:-}"
  IFS=: read -r lm lr <<<"$left"; run_cell "$lm" "$lr" 0 $((8700 + index)) & p0=$!
  if [[ -n "$right" ]]; then
    IFS=: read -r rm rr <<<"$right"; run_cell "$rm" "$rr" 1 $((8900 + index)) & p1=$!
    wait "$p0"; wait "$p1"
  else
    wait "$p0"
  fi
  index=$((index+2))
done
echo LLAMA_DIRECT_VLLM_COMPLETE
