#!/usr/bin/env bash
# Three fresh-process pairs over 30 new source-disjoint RULER sessions.
set -euo pipefail

ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
MODEL="/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Llama-3.1-8B-Instruct"
SOURCE="$ROOT/third_party/vllm-contractkv-phase19c"
OUT="$ROOT/results/submission_supplement/ruler_extended"
LOG="$ROOT/logs/submission_supplement/ruler_extended"
SESSIONS="$ROOT/results/submission_supplement/ruler_extended_sessions_v0.jsonl"
HASH="0a9e638631c1a45af65991d82c5c97f15bd7b87734a471c03f7bb602568afc49"
SCHEDULER="$SOURCE/vllm/v1/core/sched/scheduler.py"
export VLLM_STARTUP_POLLS="${VLLM_STARTUP_POLLS:-360}"
mkdir -p "$OUT" "$LOG"
cd "$ROOT"
export PYTHONPATH="$SOURCE:$ROOT${PYTHONPATH:+:$PYTHONPATH}"

"$PY" scripts/prepare_extended_ruler_sessions.py \
  --full-pool results/workload/phase14d_full_pool_v2.jsonl \
  --exclude results/end_to_end/phase19b_untouched_sessions_v0.jsonl \
  --exclude results/cross_model/llama_broad_generalization_r3/development_sessions_v0.jsonl \
  --exclude results/cross_model/llama_broad_generalization_r3/heldout_sealed_sessions_v0.jsonl \
  --count 30 --output "$SESSIONS" \
  --commitment results/submission_supplement/ruler_extended_split_commitment_v0.json

"$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action install
"$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action install
cleanup_all() {
  "$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action uninstall >/dev/null 2>&1 || true
  "$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action remove >/dev/null 2>&1 || true
}
trap cleanup_all EXIT

run_cell() {
  local repeat=$1 policy=$2 gpu=$3 port=$4
  local dir="$OUT/repeat$repeat" cell="ruler-extended-r${repeat}-${policy}"
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
  export CONTRACTKV_POLICY_HASH="$HASH" CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000
  export CONTRACTKV_MAX_DEGRADATION=1000000000 EXTRA_VLLM_ARGS="--enable-prefix-caching"
  cleanup() { bash scripts/stop_vllm_server.sh --pid-path "$pid" --port "$port" || true; }
  trap cleanup RETURN
  bash scripts/run_vllm_server.sh --phase "$cell" --model-path "$MODEL" --served-model-name llama31-8b \
    --port "$port" --gpu-ids "$gpu" --tensor-parallel-size 1 --dtype float16 \
    --max-model-len 8192 --max-num-seqs 2 --gpu-memory-utilization .88 \
    --log-path "$server_log" --pid-path "$pid"
  "$PY" scripts/phase19b_end_to_end_live.py --sessions "$SESSIONS" \
    --base-url "http://127.0.0.1:$port/v1" --model llama31-8b --model-identity "$MODEL" \
    --policy "$policy" --policy-hash "$HASH" --qualification-hash "$HASH" \
    --certificate-scope-mode qualified_session --load-tier "ruler-extended-r$repeat" \
    --concurrency 2 --turns 10 --max-tokens 96 --stable-word-limit 1500 \
    --tool-slack-ms 6000 --slo-ms 1500 --metrics-events "$metrics" --output "$output"
  cleanup
  trap - RETURN
}

for repeat in 1 2 3; do
  if (( repeat % 2 == 1 )); then raw_gpu=0; contract_gpu=1; else raw_gpu=1; contract_gpu=0; fi
  raw_port=$((8180 + repeat * 2)); contract_port=$((raw_port + 1))
  run_cell "$repeat" raw-order "$raw_gpu" "$raw_port" & p0=$!
  sleep 2
  run_cell "$repeat" contractkv-full "$contract_gpu" "$contract_port" & p1=$!
  failed=0; wait "$p0" || failed=1; wait "$p1" || failed=1
  [[ $failed -eq 0 ]] || exit 31
done

cells=(); pairs=()
for repeat in 1 2 3; do
  cells+=(--cell "llama-ruler-extended,$repeat,raw-order,$OUT/repeat$repeat/raw-order.jsonl")
  cells+=(--cell "llama-ruler-extended,$repeat,contractkv-full,$OUT/repeat$repeat/contractkv-full.jsonl")
  pairs+=(--pair "$repeat,$OUT/repeat$repeat/raw-order.jsonl,$OUT/repeat$repeat/contractkv-full.jsonl")
done
"$PY" scripts/summarize_submission_repeats.py "${cells[@]}" --slo-ms 1500 \
  --raw-output results/submission_supplement/ruler_extended_cells_v0.csv \
  --paired-output results/submission_supplement/ruler_extended_pairs_v0.csv \
  --aggregate-output results/submission_supplement/ruler_extended_aggregate_v0.csv \
  --json-output results/submission_supplement/ruler_extended_summary_v0.json
"$PY" scripts/score_llama_qualified_replay.py --sessions "$SESSIONS" "${pairs[@]}" \
  --output results/submission_supplement/ruler_extended_quality_v0.csv \
  --summary results/submission_supplement/ruler_extended_quality_summary_v0.json
"$PY" scripts/summarize_extended_ruler.py --root "$OUT" \
  --output results/submission_supplement/ruler_extended_cluster_bootstrap_v0.csv \
  --json-output results/submission_supplement/ruler_extended_cluster_bootstrap_v0.json
echo EXTENDED_RULER_REPLAY_COMPLETE
