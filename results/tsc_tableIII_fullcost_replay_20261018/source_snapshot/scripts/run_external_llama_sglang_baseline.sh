#!/usr/bin/env bash
# Fresh SGLang RadixAttention B2/B4 replay on the sealed Llama workload.
set -euo pipefail

ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
SGLANG_PY="${SGLANG_PY:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/envs/contractkv-sglang/bin/python}"
MODEL="/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Llama-3.1-8B-Instruct"
SESSIONS="${SESSIONS:-$ROOT/results/cross_model/llama_broad_generalization_r3/heldout_sealed_sessions_v0.jsonl}"
QUALIFICATION="$ROOT/results/cross_model/llama_broad_generalization_r3/llama_broad_qualification_v0.json"
CERTIFIED_SESSIONS="$ROOT/results/cross_model/llama_broad_generalization_r3/repeat1/r1-contract.jsonl"
MODE_RIGHT="${MODE_RIGHT:-certified}"
REPEATS="${REPEATS:-1 2 3}"
OUT="${OUT:-$ROOT/results/external_baseline/llama_radix_certified}"; LOG="${LOG:-$ROOT/logs/external_baseline/llama_radix_certified}"
CACHE_ROOT="/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/runtime_cache/sglang_llama_radix"
mkdir -p "$OUT" "$LOG" "$CACHE_ROOT"; cd "$ROOT"
export XDG_CACHE_HOME="$CACHE_ROOT/xdg" TRITON_CACHE_DIR="$CACHE_ROOT/triton"
export TORCH_EXTENSIONS_DIR="$CACHE_ROOT/torch_extensions" FLASHINFER_JIT_DIR="$CACHE_ROOT/flashinfer"

complete() {
  [[ -s "$1" && -s "$2" ]] || return 1
  "$SGLANG_PY" -c 'import json,sys; raw,summary=sys.argv[1:]; d=json.load(open(summary)); raise SystemExit(0 if sum(bool(x.strip()) for x in open(raw)) == 500 and d.get("future_requests") == 450 and d.get("completed_requests") == 450 else 1)' "$1" "$2"
}

run_cell() {
  local repeat=$1 mode=$2 gpu=$3 port=$4
  local tag="llama-r${repeat}-${mode}"
  local raw="$OUT/${tag}.jsonl" summary="$OUT/${tag}_summary.json"
  local pid="$LOG/${tag}.pid" server_log="$LOG/${tag}.log"
  complete "$raw" "$summary" && { echo "SKIP_COMPLETE $tag"; return; }
  rm -f "$raw" "$summary" "$pid"
  export CUDA_VISIBLE_DEVICES="$gpu" HF_HOME="/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/datasets/hf_cache"
  setsid "$SGLANG_PY" -m sglang.launch_server --model-path "$MODEL" --served-model-name llama31-8b \
    --host 127.0.0.1 --port "$port" --dtype float16 --mem-fraction-static .88 \
    --context-length 8192 --max-running-requests 2 --enable-metrics \
    --attention-backend triton --sampling-backend pytorch >"$server_log" 2>&1 &
  local server=$!; echo "$server" > "$pid"
  cleanup(){ kill -TERM -- "-$server" 2>/dev/null || true; sleep 2; kill -KILL -- "-$server" 2>/dev/null || true; wait "$server" 2>/dev/null || true; }
  trap cleanup RETURN
  for _ in $(seq 1 240); do curl -sf "http://127.0.0.1:$port/v1/models" >/dev/null && break; sleep 2; done
  curl -sf "http://127.0.0.1:$port/v1/models" >/dev/null
  args=(--sessions "$SESSIONS" --qualification-manifest "$QUALIFICATION" \
    --base-url "http://127.0.0.1:$port/v1" --model llama31-8b --model-path "$MODEL" --backend-label "$tag" \
    --mode "$mode" --concurrency 2 --turns 10 --stable-word-limit 1500 --stable-pieces 16 --max-tokens 96 --slo-ms 1500 \
    --output "$raw" --summary-output "$summary")
  [[ "$mode" == certified ]] && args+=(--certificate-source "$CERTIFIED_SESSIONS")
  "$SGLANG_PY" scripts/run_external_llama_radix_replay.py "${args[@]}"
  cleanup; trap - RETURN
}

for repeat in $REPEATS; do
  if (( repeat % 2 )); then
    run_cell "$repeat" raw 0 $((8800 + repeat)) & p0=$!
    run_cell "$repeat" "$MODE_RIGHT" 1 $((8900 + repeat)) & p1=$!
  else
    run_cell "$repeat" raw 1 $((8800 + repeat)) & p0=$!
    run_cell "$repeat" "$MODE_RIGHT" 0 $((8900 + repeat)) & p1=$!
  fi
  wait "$p0"; wait "$p1"
done
echo LLAMA_SGLANG_BASELINE_COMPLETE
