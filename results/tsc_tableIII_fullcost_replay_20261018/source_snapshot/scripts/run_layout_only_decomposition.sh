#!/usr/bin/env bash
# Run the missing same-runtime layout-only cells on one GPU per model.
set -euo pipefail

ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
OUT="$ROOT/results/submission_supplement/layout_only_safe"
LOG="$ROOT/logs/submission_supplement"
export VLLM_STARTUP_POLLS="${VLLM_STARTUP_POLLS:-360}"
mkdir -p "$OUT" "$LOG"
cd "$ROOT"

cleanup_source() {
  local source=$1 model_key=$2
  "$PY" scripts/install_vllm_v1_prefix_metrics_probe.py \
    --scheduler "$source/vllm/v1/core/sched/scheduler.py" --action uninstall >/dev/null 2>&1 || true
  if [[ "$model_key" == "mistral" ]]; then
    "$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py \
      --scheduler "$source/vllm/v1/core/sched/scheduler.py" --action remove >/dev/null 2>&1 || true
  fi
}

run_model() {
  local model_key=$1 gpu=$2 port=$3 source=$4 model_path=$5 served=$6 sessions=$7
  local policy_hash=$8 max_tokens=$9 stable_limit=${10}
  export PYTHONPATH="$source:$ROOT${PYTHONPATH:+:$PYTHONPATH}"
  "$PY" scripts/install_vllm_v1_prefix_metrics_probe.py \
    --scheduler "$source/vllm/v1/core/sched/scheduler.py" --action install
  if [[ "$model_key" == "mistral" ]]; then
    "$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py \
      --scheduler "$source/vllm/v1/core/sched/scheduler.py" --action install
  fi
  trap 'cleanup_source "$source" "$model_key"' RETURN
  for repeat in 1 2 3; do
    local dir="$OUT/$model_key/repeat$repeat" cell="$model_key-layout-only-r$repeat"
    local metrics="$dir/offline-frozen-safe-compiled_metrics.jsonl" output="$dir/offline-frozen-safe-compiled.jsonl"
    local pid="$LOG/$cell.pid" server_log="$LOG/${cell}_server.log"
    mkdir -p "$dir"
    if [[ -s "$metrics" && -s "$output" && "$(wc -l < "$output")" -eq 500 ]]; then
      echo "SKIP completed $cell"
      continue
    fi
    rm -f "$metrics" "$output" "$pid"
    export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1 CONTRACTKV_PREFIX_METRICS_LOG="$metrics"
    export CONTRACTKV_POLICY_HASH="$policy_hash" CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000
    export CONTRACTKV_MAX_DEGRADATION=1000000000 EXTRA_VLLM_ARGS="--enable-prefix-caching"
    bash scripts/run_vllm_server.sh --phase "$cell" --model-path "$model_path" --served-model-name "$served" \
      --port "$port" --gpu-ids "$gpu" --tensor-parallel-size 1 --dtype float16 \
      --max-model-len 8192 --max-num-seqs 2 --gpu-memory-utilization .88 \
      --log-path "$server_log" --pid-path "$pid"
    "$PY" scripts/phase19b_end_to_end_live.py --sessions "$sessions" \
      --base-url "http://127.0.0.1:$port/v1" --model "$served" --model-identity "$model_path" \
      --policy offline-frozen-safe-compiled --safe-session-source "$ROOT/results/submission_repeats/$model_key/repeat1/contractkv-full.jsonl" \
      --policy-hash "$policy_hash" --qualification-hash "$policy_hash" \
      --certificate-scope-mode qualified_session --load-tier "layout-only-r$repeat" \
      --concurrency 2 --turns 10 --max-tokens "$max_tokens" --stable-word-limit "$stable_limit" \
      --tool-slack-ms 2000 --slo-ms 1500 --metrics-events "$metrics" --output "$output"
    bash scripts/stop_vllm_server.sh --pid-path "$pid" --port "$port" || true
  done
  cleanup_source "$source" "$model_key"
  trap - RETURN
}

if nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | grep -q '[0-9]'; then
  echo "GPU compute process already exists; refusing to mix decomposition cells" >&2
  exit 20
fi

run_model qwen 0 8161 "$ROOT/third_party/vllm-contractkv" \
  "/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-8B" qwen3-8b \
  "$ROOT/results/end_to_end/phase19b_untouched_sessions_v0.jsonl" \
  "55e10dc4f54daf428b382a35fe8a8feeded5b4b3f34752f36f45c8f825df1ee4" 96 2600 &
p0=$!
run_model mistral 1 8162 "$ROOT/third_party/vllm-contractkv-phase19c" \
  "/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Mistral-7B-Instruct-v0.3" mistral7b \
  "$ROOT/results/mistral/heldout_sealed_sessions_v0.jsonl" \
  "f5d99ddf2bb14dc9d3e0a92040f337682cbb9ab93baef4e3be5d43d9106488d8" 128 1500 &
p1=$!
failed=0
wait "$p0" || failed=1
wait "$p1" || failed=1
[[ $failed -eq 0 ]] || exit 31

"$PY" scripts/summarize_layout_only_decomposition.py \
  --submission-root "$ROOT/results/submission_repeats" --layout-root "$OUT" \
  --output "$ROOT/results/submission_supplement/layout_only_decomposition_v0.csv" \
  --json-output "$ROOT/results/submission_supplement/layout_only_decomposition_v0.json"
echo LAYOUT_ONLY_DECOMPOSITION_COMPLETE
