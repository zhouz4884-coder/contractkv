#!/usr/bin/env bash
# Qwen/Mistral replay on the exact frozen 30-session Llama extension scope.
set -euo pipefail

ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
SOURCE="$ROOT/third_party/vllm-contractkv-phase19c"
SESSIONS="$ROOT/results/submission_supplement/ruler_extended_sessions_v0.jsonl"
COMMITMENT="$ROOT/results/submission_supplement/ruler_extended_split_commitment_v0.json"
EXPECTED_SHA="7fe10a55f82056125b6acb478aa24bd4883c12c4f6bfd19b3dedfd1f6e13f616"
BASE="$ROOT/results/submission_supplement/common_ruler"
LOG="$ROOT/logs/submission_supplement/common_ruler"
SCHEDULER="$SOURCE/vllm/v1/core/sched/scheduler.py"
export VLLM_STARTUP_POLLS="${VLLM_STARTUP_POLLS:-360}"
mkdir -p "$BASE" "$LOG"
cd "$ROOT"
export PYTHONPATH="$SOURCE:$ROOT${PYTHONPATH:+:$PYTHONPATH}"

"$PY" scripts/verify_frozen_ruler_sessions.py --sessions "$SESSIONS" --commitment "$COMMITMENT" \
  --expected-sha256 "$EXPECTED_SHA" --expected-count 30 --expected-turns 10
"$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action install
"$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action install
cleanup_all() {
  "$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action uninstall >/dev/null 2>&1 || true
  "$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action remove >/dev/null 2>&1 || true
}
trap cleanup_all EXIT

run_cell() {
  local label=$1 model_path=$2 served=$3 hash=$4 repeat=$5 policy=$6 gpu=$7 port=$8
  local dir="$BASE/$label/repeat$repeat" cell="common-ruler-${label}-r${repeat}-${policy}"
  local metrics="$dir/${policy}_metrics.jsonl" output="$dir/${policy}.jsonl"
  local pid="$LOG/$cell.pid" server_log="$LOG/${cell}_server.log"
  mkdir -p "$dir"
  local output_rows=0 metrics_rows=0
  [[ -f "$output" ]] && output_rows=$(wc -l < "$output")
  [[ -f "$metrics" ]] && metrics_rows=$(wc -l < "$metrics")
  if [[ "$output_rows" -eq 300 && "$metrics_rows" -gt 0 ]]; then
    echo "SKIP completed $cell ($output_rows request rows, $metrics_rows metric rows)"
    return
  fi
  rm -f "$metrics" "$output" "$pid"
  export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1 CONTRACTKV_PREFIX_METRICS_LOG="$metrics"
  export CONTRACTKV_POLICY_HASH="$hash" CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000
  export CONTRACTKV_MAX_DEGRADATION=1000000000 EXTRA_VLLM_ARGS="--enable-prefix-caching"
  cleanup() { bash scripts/stop_vllm_server.sh --pid-path "$pid" --port "$port" || true; }
  trap cleanup RETURN
  VLLM_CACHE_ROOT="$ROOT/cache/common-ruler/$cell/vllm" \
  TRITON_CACHE_DIR="$ROOT/cache/common-ruler/$cell/triton" \
  bash scripts/run_vllm_server.sh --phase "$cell" --model-path "$model_path" --served-model-name "$served" \
    --port "$port" --gpu-ids "$gpu" --tensor-parallel-size 1 --dtype float16 \
    --max-model-len 8192 --max-num-seqs 2 --gpu-memory-utilization .88 \
    --log-path "$server_log" --pid-path "$pid"
  "$PY" scripts/phase19b_end_to_end_live.py --sessions "$SESSIONS" \
    --base-url "http://127.0.0.1:$port/v1" --model "$served" --model-identity "$model_path" \
    --policy "$policy" --policy-hash "$hash" --qualification-hash "$hash" \
    --certificate-scope-mode qualified_session --load-tier "common-ruler-${label}-r$repeat" \
    --concurrency 2 --turns 10 --max-tokens 96 --stable-word-limit 1500 \
    --tool-slack-ms 6000 --slo-ms 1500 --metrics-events "$metrics" --output "$output"
  cleanup
  trap - RETURN
}

run_model() {
  local label=$1 model_path=$2 served=$3 hash=$4 base_port=$5
  for repeat in 1 2 3; do
    if (( repeat % 2 == 1 )); then raw_gpu=0; contract_gpu=1; else raw_gpu=1; contract_gpu=0; fi
    raw_port=$((base_port + repeat * 2)); contract_port=$((raw_port + 1))
    run_cell "$label" "$model_path" "$served" "$hash" "$repeat" raw-order "$raw_gpu" "$raw_port" & p0=$!
    sleep 2
    run_cell "$label" "$model_path" "$served" "$hash" "$repeat" contractkv-full "$contract_gpu" "$contract_port" & p1=$!
    failed=0; wait "$p0" || failed=1; wait "$p1" || failed=1
    [[ $failed -eq 0 ]] || exit 31
  done
  cells=(); pairs=()
  for repeat in 1 2 3; do
    cells+=(--cell "$label,$repeat,raw-order,$BASE/$label/repeat$repeat/raw-order.jsonl")
    cells+=(--cell "$label,$repeat,contractkv-full,$BASE/$label/repeat$repeat/contractkv-full.jsonl")
    pairs+=(--pair "$repeat,$BASE/$label/repeat$repeat/raw-order.jsonl,$BASE/$label/repeat$repeat/contractkv-full.jsonl")
  done
  "$PY" scripts/summarize_submission_repeats.py "${cells[@]}" --slo-ms 1500 \
    --raw-output "results/submission_supplement/common_ruler_${label}_cells_v0.csv" \
    --paired-output "results/submission_supplement/common_ruler_${label}_pairs_v0.csv" \
    --aggregate-output "results/submission_supplement/common_ruler_${label}_aggregate_v0.csv" \
    --json-output "results/submission_supplement/common_ruler_${label}_summary_v0.json"
  "$PY" scripts/score_common_ruler_replay.py --model "$label" --sessions "$SESSIONS" "${pairs[@]}" \
    --output "results/submission_supplement/common_ruler_${label}_quality_v0.csv" \
    --summary "results/submission_supplement/common_ruler_${label}_quality_summary_v0.json"
}

run_model qwen /media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-8B qwen3-8b \
  55e10dc4f54daf428b382a35fe8a8feeded5b4b3f34752f36f45c8f825df1ee4 8220
run_model mistral /media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Mistral-7B-Instruct-v0.3 mistral7b \
  f5d99ddf2bb14dc9d3e0a92040f337682cbb9ab93baef4e3be5d43d9106488d8 8240

"$PY" scripts/summarize_common_ruler_cross_model.py \
  --model-root "Qwen3-8B,$BASE/qwen" \
  --model-root "Mistral-7B-Instruct-v0.3,$BASE/mistral" \
  --model-root "Llama-3.1-8B-Instruct,$ROOT/results/submission_supplement/ruler_extended" \
  --session-sha256 "$EXPECTED_SHA" \
  --output results/submission_supplement/common_ruler_cross_model_bootstrap_v0.csv \
  --json-output results/submission_supplement/common_ruler_cross_model_bootstrap_v0.json
"$PY" scripts/summarize_common_ruler_quality.py \
  --quality "Qwen3-8B,results/submission_supplement/common_ruler_qwen_quality_v0.csv" \
  --quality "Mistral-7B-Instruct-v0.3,results/submission_supplement/common_ruler_mistral_quality_v0.csv" \
  --quality "Llama-3.1-8B-Instruct,results/submission_supplement/ruler_extended_quality_v0.csv" \
  --output results/submission_supplement/common_ruler_cross_model_quality_v0.csv \
  --json-output results/submission_supplement/common_ruler_cross_model_quality_v0.json
echo COMMON_RULER_CROSS_MODEL_COMPLETE
