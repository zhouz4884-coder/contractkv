#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
OUT="$ROOT/results/submission_repeats"; LOG="$ROOT/logs/submission_repeats"
cd "$ROOT"; mkdir -p "$OUT" "$LOG"

if nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | grep -q '[0-9]'; then
  echo "GPU compute process already exists; refusing to mix submission repeats" >&2
  exit 20
fi

cleanup_all(){
  for source in "$ROOT/third_party/vllm-contractkv" "$ROOT/third_party/vllm-contractkv-phase19c"; do
    "$PY" scripts/install_vllm_v1_prefix_metrics_probe.py \
      --scheduler "$source/vllm/v1/core/sched/scheduler.py" --action uninstall >/dev/null 2>&1 || true
  done
  "$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py \
    --scheduler "$ROOT/third_party/vllm-contractkv-phase19c/vllm/v1/core/sched/scheduler.py" \
    --action remove >/dev/null 2>&1 || true
}
trap cleanup_all EXIT

run_cell(){
  local model_key=$1 repeat=$2 policy=$3 gpu=$4 port=$5 source=$6 model_path=$7 served=$8 sessions=$9
  local policy_hash=${10} max_tokens=${11} stable_limit=${12}
  local cell="$model_key-r${repeat}-${policy}" dir="$OUT/$model_key/repeat${repeat}"
  mkdir -p "$dir"
  (
    set -euo pipefail
    export PYTHONPATH="$source:$ROOT${PYTHONPATH:+:$PYTHONPATH}"
    local metrics="$dir/${policy}_metrics.jsonl" output="$dir/${policy}.jsonl"
    local pid="$LOG/${cell}.pid" server_log="$LOG/${cell}_server.log"
    rm -f "$metrics" "$output" "$pid"
    export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1 CONTRACTKV_PREFIX_METRICS_LOG="$metrics"
    export CONTRACTKV_POLICY_HASH="$policy_hash" CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000
    export CONTRACTKV_MAX_DEGRADATION=1000000000 EXTRA_VLLM_ARGS="--enable-prefix-caching"
    cleanup(){ bash scripts/stop_vllm_server.sh --pid-path "$pid" --port "$port" || true; }
    trap cleanup EXIT
    bash scripts/run_vllm_server.sh --phase "$cell" --model-path "$model_path" --served-model-name "$served" \
      --port "$port" --gpu-ids "$gpu" --tensor-parallel-size 1 --dtype float16 \
      --max-model-len 8192 --max-num-seqs 2 --gpu-memory-utilization .88 \
      --log-path "$server_log" --pid-path "$pid"
    "$PY" scripts/phase19b_end_to_end_live.py --sessions "$sessions" \
      --base-url "http://127.0.0.1:$port/v1" --model "$served" --model-identity "$model_path" \
      --policy "$policy" --policy-hash "$policy_hash" --qualification-hash "$policy_hash" \
      --certificate-scope-mode qualified_session --load-tier "submission-r${repeat}" \
      --concurrency 2 --turns 10 --max-tokens "$max_tokens" --stable-word-limit "$stable_limit" \
      --tool-slack-ms 2000 --slo-ms 1500 --metrics-events "$metrics" --output "$output"
  )
}

run_model(){
  local model_key=$1 source=$2 model_path=$3 served=$4 sessions=$5 policy_hash=$6 max_tokens=$7 stable_limit=$8 port_base=$9
  local scheduler="$source/vllm/v1/core/sched/scheduler.py"
  export PYTHONPATH="$source:$ROOT${PYTHONPATH:+:$PYTHONPATH}"
  "$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$scheduler" --action install
  if [[ "$model_key" == "mistral" ]]; then
    "$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$scheduler" --action install
  fi
  for repeat in 1 2 3; do
    local raw_gpu contract_gpu raw_port contract_port
    if (( repeat % 2 == 1 )); then raw_gpu=0; contract_gpu=1; else raw_gpu=1; contract_gpu=0; fi
    raw_port=$((port_base + repeat * 2)); contract_port=$((raw_port + 1))
    if (( repeat == 2 )); then
      run_cell "$model_key" "$repeat" contractkv-full "$contract_gpu" "$contract_port" "$source" "$model_path" "$served" "$sessions" "$policy_hash" "$max_tokens" "$stable_limit" & p1=$!
      sleep 2
      run_cell "$model_key" "$repeat" raw-order "$raw_gpu" "$raw_port" "$source" "$model_path" "$served" "$sessions" "$policy_hash" "$max_tokens" "$stable_limit" & p0=$!
    else
      run_cell "$model_key" "$repeat" raw-order "$raw_gpu" "$raw_port" "$source" "$model_path" "$served" "$sessions" "$policy_hash" "$max_tokens" "$stable_limit" & p0=$!
      sleep 2
      run_cell "$model_key" "$repeat" contractkv-full "$contract_gpu" "$contract_port" "$source" "$model_path" "$served" "$sessions" "$policy_hash" "$max_tokens" "$stable_limit" & p1=$!
    fi
    failed=0; wait "$p0" || failed=1; wait "$p1" || failed=1
    [[ $failed -eq 0 ]] || exit 31
  done
  "$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$scheduler" --action uninstall
  if [[ "$model_key" == "mistral" ]]; then
    "$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$scheduler" --action remove
  fi
}

QWEN_SOURCE="$ROOT/third_party/vllm-contractkv"
MISTRAL_SOURCE="$ROOT/third_party/vllm-contractkv-phase19c"
run_model qwen "$QWEN_SOURCE" \
  "/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-8B" qwen3-8b \
  "$ROOT/results/end_to_end/phase19b_untouched_sessions_v0.jsonl" \
  "55e10dc4f54daf428b382a35fe8a8feeded5b4b3f34752f36f45c8f825df1ee4" 96 2600 8130
run_model mistral "$MISTRAL_SOURCE" \
  "/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Mistral-7B-Instruct-v0.3" mistral7b \
  "$ROOT/results/mistral/heldout_sealed_sessions_v0.jsonl" \
  "f5d99ddf2bb14dc9d3e0a92040f337682cbb9ab93baef4e3be5d43d9106488d8" 128 1500 8140

repairs=()
for model in qwen mistral; do
  for repeat in 1 2 3; do
    repairs+=(--input "$OUT/$model/repeat$repeat/contractkv-full.jsonl")
  done
done
"$PY" scripts/repair_submission_scope_telemetry.py "${repairs[@]}" \
  --manifest "$OUT/scope_telemetry_repair_manifest_v0.json"

cells=()
for model in qwen mistral; do
  for repeat in 1 2 3; do
    cells+=(--cell "$model,$repeat,raw-order,$OUT/$model/repeat$repeat/raw-order.jsonl")
    cells+=(--cell "$model,$repeat,contractkv-full,$OUT/$model/repeat$repeat/contractkv-full.jsonl")
  done
done
"$PY" scripts/summarize_submission_repeats.py "${cells[@]}" --slo-ms 1500 \
  --raw-output "$OUT/submission_repeat_cells_v0.csv" \
  --paired-output "$OUT/submission_repeat_pairs_v0.csv" \
  --aggregate-output "$OUT/submission_repeat_aggregate_v0.csv" \
  --json-output "$OUT/submission_repeat_summary_v0.json"
echo SUBMISSION_REPEATS_COMPLETE
