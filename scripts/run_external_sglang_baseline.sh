#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
SGLANG_PY="${SGLANG_PY:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/envs/contractkv-sglang/bin/python}"
OUT="$ROOT/results/external_baseline"; LOG="$ROOT/logs/external_baseline"
CACHE_ROOT="/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/runtime_cache/sglang"
cd "$ROOT"; mkdir -p "$OUT" "$LOG" "$CACHE_ROOT/xdg" "$CACHE_ROOT/triton" "$CACHE_ROOT/torch_extensions" "$CACHE_ROOT/flashinfer"
exec 9>"$LOG/driver.lock"
flock -n 9 || { echo "another SGLang baseline driver holds $LOG/driver.lock" >&2; exit 40; }
export PATH="$(dirname "$SGLANG_PY"):$PATH"
export XDG_CACHE_HOME="$CACHE_ROOT/xdg"
export TRITON_CACHE_DIR="$CACHE_ROOT/triton"
export TORCH_EXTENSIONS_DIR="$CACHE_ROOT/torch_extensions"
export FLASHINFER_JIT_DIR="$CACHE_ROOT/flashinfer"

cell_complete(){
  local raw=$1 summary=$2
  [[ -s "$raw" && -s "$summary" ]] || return 1
  "$SGLANG_PY" -c 'import json,sys; raw,summary=sys.argv[1:]; rows=sum(1 for line in open(raw,encoding="utf-8") if line.strip()); data=json.load(open(summary,encoding="utf-8")); raise SystemExit(0 if rows == 500 and data.get("future_requests") == 450 and data.get("completed_requests") == 450 and data.get("completion_rate") == 1.0 else 1)' "$raw" "$summary"
}

run_cell(){
  local model_key=$1 repeat=$2 layout=$3 gpu=$4 port=$5 model=$6 served=$7 sessions=$8 safe_source=$9
  local max_tokens=${10} stable_limit=${11}
  local label="sglang-${model_key}-r${repeat}-${layout}"
  local pid="$LOG/$label.pid" log="$LOG/$label.log"
  if cell_complete "$OUT/${label}.jsonl" "$OUT/${label}_summary.json"; then
    echo "SKIP_COMPLETE $label"
    return 0
  fi
  rm -f "$pid" "$OUT/${label}.jsonl" "$OUT/${label}_summary.json"
  (
    set -euo pipefail
    export CUDA_VISIBLE_DEVICES="$gpu" HF_HOME="/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/datasets/hf_cache"
    setsid "$SGLANG_PY" -m sglang.launch_server --model-path "$model" --served-model-name "$served" \
      --host 127.0.0.1 --port "$port" --dtype float16 --mem-fraction-static .88 \
      --context-length 8192 --max-running-requests 2 --enable-metrics \
      --attention-backend triton --sampling-backend pytorch > "$log" 2>&1 & server=$!
    echo "$server" > "$pid"
    cleanup(){
      kill -TERM -- "-$server" 2>/dev/null || true
      for _ in $(seq 1 30); do
        kill -0 "$server" 2>/dev/null || break
        sleep 1
      done
      kill -KILL -- "-$server" 2>/dev/null || true
      wait "$server" 2>/dev/null || true
    }
    trap cleanup EXIT
    for _ in $(seq 1 180); do
      curl -sf "http://127.0.0.1:$port/v1/models" >/dev/null && break
      sleep 2
    done
    curl -sf "http://127.0.0.1:$port/v1/models" >/dev/null
    args=(--sessions "$sessions" --base-url "http://127.0.0.1:$port/v1" \
      --model "$served" --model-path "$model" --backend-label "$label" \
      --layout-policy "$layout" --concurrency 2 --turns 10 \
      --stable-word-limit "$stable_limit" --max-tokens "$max_tokens" --slo-ms 1500 \
      --output "$OUT/${label}.jsonl" --summary-output "$OUT/${label}_summary.json")
    if [[ "$layout" == "offline-safe-compiled" ]]; then
      args+=(--safe-session-source "$safe_source")
    fi
    "$SGLANG_PY" scripts/run_external_sglang_raw_replay.py "${args[@]}"
  )
}

run_model(){
  local model_key=$1 model=$2 served=$3 sessions=$4 safe_source=$5 max_tokens=$6 stable_limit=$7 port_base=$8
  for repeat in 1 2 3; do
    local raw_gpu compiled_gpu raw_port compiled_port
    if (( repeat % 2 == 1 )); then raw_gpu=0; compiled_gpu=1; else raw_gpu=1; compiled_gpu=0; fi
    raw_port=$((port_base + repeat * 2)); compiled_port=$((raw_port + 1))
    run_cell "$model_key" "$repeat" raw-order "$raw_gpu" "$raw_port" "$model" "$served" "$sessions" "$safe_source" "$max_tokens" "$stable_limit" & p0=$!
    sleep 2
    run_cell "$model_key" "$repeat" offline-safe-compiled "$compiled_gpu" "$compiled_port" "$model" "$served" "$sessions" "$safe_source" "$max_tokens" "$stable_limit" & p1=$!
    failed=0; wait "$p0" || failed=1; wait "$p1" || failed=1
    [[ $failed -eq 0 ]] || exit 31
  done
}

run_model qwen \
  "/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-8B" qwen3-8b \
  "$ROOT/results/end_to_end/phase19b_untouched_sessions_v0.jsonl" \
  "$ROOT/results/submission_repeats/qwen/repeat1/contractkv-full.jsonl" 96 2600 8150
run_model mistral \
  "/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Mistral-7B-Instruct-v0.3" mistral7b \
  "$ROOT/results/mistral/heldout_sealed_sessions_v0.jsonl" \
  "$ROOT/results/submission_repeats/mistral/repeat1/contractkv-full.jsonl" 128 1500 8170

"$SGLANG_PY" scripts/summarize_external_system_matrix.py \
  --submission-summary "$ROOT/results/submission_repeats/submission_repeat_summary_v0.json" \
  --external-dir "$OUT" --output "$OUT/external_prefix_baseline_summary_v0.json" \
  --csv-output "$OUT/external_system_matrix_v0.csv"
echo EXTERNAL_SGLANG_BASELINE_COMPLETE
