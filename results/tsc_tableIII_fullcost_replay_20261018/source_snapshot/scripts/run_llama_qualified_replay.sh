#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
MODEL="${MODEL_PATH:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Llama-3.1-8B-Instruct}"
SOURCE="${SOURCE_VLLM:-$ROOT/third_party/vllm-contractkv-phase19c}"
OUT="$ROOT/results/cross_model/llama_qualified_replay"; LOG="$ROOT/logs/llama_qualified_replay"
SCHEDULER="$SOURCE/vllm/v1/core/sched/scheduler.py"
DEV="$ROOT/results/cross_model/phase20c_development_two_tier_v0.jsonl"
HELD="$ROOT/results/cross_model/phase20d_heldout_sealed_sessions_v0.jsonl"
MANIFEST="$OUT/llama_task_qualification_v0.json"; QUALIFIED="$OUT/qualified_heldout_sessions_v0.jsonl"
cd "$ROOT"; mkdir -p "$OUT" "$LOG"; export PYTHONPATH="$SOURCE:$ROOT${PYTHONPATH:+:$PYTHONPATH}"
"$PY" scripts/freeze_llama_task_qualification.py --development "$DEV" --heldout "$HELD" \
  --model-identity "$MODEL" --manifest "$MANIFEST" --qualified-heldout "$QUALIFIED"
HASH=$("$PY" -c "import json;print(json.load(open('$MANIFEST'))['qualification_hash'])")
"$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action install
"$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action install
cleanup_all(){
  "$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action uninstall >/dev/null 2>&1 || true
  "$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action remove >/dev/null 2>&1 || true
}
trap cleanup_all EXIT

run_cell(){
  local repeat=$1 policy=$2 gpu=$3 port=$4
  local dir="$OUT/repeat$repeat" cell="llama-qualified-r${repeat}-${policy}"
  mkdir -p "$dir"
  (
    set -euo pipefail
    local metrics="$dir/${policy}_metrics.jsonl" output="$dir/${policy}.jsonl"
    local pid="$LOG/${cell}.pid" log="$LOG/${cell}_server.log"
    rm -f "$metrics" "$output" "$pid"
    export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1 CONTRACTKV_PREFIX_METRICS_LOG="$metrics"
    export CONTRACTKV_POLICY_HASH="$HASH" CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000 CONTRACTKV_MAX_DEGRADATION=1000000000
    export EXTRA_VLLM_ARGS="--enable-prefix-caching"
    cleanup(){ bash scripts/stop_vllm_server.sh --pid-path "$pid" --port "$port" || true; }
    trap cleanup EXIT
    bash scripts/run_vllm_server.sh --phase "$cell" --model-path "$MODEL" --served-model-name llama31-8b \
      --port "$port" --gpu-ids "$gpu" --tensor-parallel-size 1 --dtype float16 --max-model-len 8192 \
      --max-num-seqs 2 --gpu-memory-utilization .88 --log-path "$log" --pid-path "$pid"
    "$PY" scripts/phase19b_end_to_end_live.py --sessions "$QUALIFIED" --base-url "http://127.0.0.1:$port/v1" \
      --model llama31-8b --model-identity "$MODEL" --policy "$policy" --policy-hash "$HASH" \
      --qualification-hash "$HASH" --certificate-scope-mode qualified_session --load-tier "llama-qualified-r$repeat" \
      --concurrency 2 --turns 10 --max-tokens 96 --stable-word-limit 2600 --tool-slack-ms 6000 \
      --slo-ms 1500 --metrics-events "$metrics" --output "$output"
  )
}

for repeat in 1 2 3; do
  if (( repeat % 2 == 1 )); then raw_gpu=0; contract_gpu=1; else raw_gpu=1; contract_gpu=0; fi
  raw_port=$((8400 + repeat * 2)); contract_port=$((raw_port + 1))
  if (( repeat == 2 )); then
    run_cell "$repeat" contractkv-full "$contract_gpu" "$contract_port" & p1=$!; sleep 2
    run_cell "$repeat" raw-order "$raw_gpu" "$raw_port" & p0=$!
  else
    run_cell "$repeat" raw-order "$raw_gpu" "$raw_port" & p0=$!; sleep 2
    run_cell "$repeat" contractkv-full "$contract_gpu" "$contract_port" & p1=$!
  fi
  failed=0; wait "$p0" || failed=1; wait "$p1" || failed=1; [[ $failed -eq 0 ]] || exit 31
done
cells=(); pairs=()
for repeat in 1 2 3; do
  cells+=(--cell "llama-qualified,$repeat,raw-order,$OUT/repeat$repeat/raw-order.jsonl")
  cells+=(--cell "llama-qualified,$repeat,contractkv-full,$OUT/repeat$repeat/contractkv-full.jsonl")
  pairs+=(--pair "$repeat,$OUT/repeat$repeat/raw-order.jsonl,$OUT/repeat$repeat/contractkv-full.jsonl")
done
"$PY" scripts/summarize_submission_repeats.py "${cells[@]}" --slo-ms 1500 \
  --raw-output "$OUT/cells_v0.csv" --paired-output "$OUT/pairs_v0.csv" \
  --aggregate-output "$OUT/aggregate_v0.csv" --json-output "$OUT/summary_v0.json"
"$PY" scripts/score_llama_qualified_replay.py --sessions "$QUALIFIED" "${pairs[@]}" \
  --output "$OUT/quality_pairs_v0.csv" --summary "$OUT/quality_summary_v0.json"
echo LLAMA_QUALIFIED_REPLAY_COMPLETE
