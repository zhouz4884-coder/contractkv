#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
MODEL="${MODEL_PATH:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Llama-3.1-8B-Instruct}"
SOURCE="${SOURCE_VLLM:-$ROOT/third_party/vllm-contractkv-phase19c}"
OUT_NAME="${OUT_NAME:-llama_broad_generalization_r1}"
OUT="$ROOT/results/cross_model/$OUT_NAME"
LOG="$ROOT/logs/$OUT_NAME"
DEV="$OUT/development_sessions_v0.jsonl"
HELD="$OUT/heldout_sealed_sessions_v0.jsonl"
SPLIT="$OUT/split_commitment_v0.json"
MANIFEST="$OUT/llama_broad_qualification_v0.json"
SCHEDULER="$SOURCE/vllm/v1/core/sched/scheduler.py"
RUN_SCOPE="${RUN_SCOPE:-all}"
LADDER="${LADDER:-L0=0,L1=.0625,L2=.25,L3=.5}"
SELECTION_SALT="${SELECTION_SALT:-llama-broad-r1-v1}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-8192}"
MIN_COVERAGE="${MIN_COVERAGE:-.4}"
STABLE_PIECES="${STABLE_PIECES:-16}"
LADDER_JSON="${LADDER_JSON:-}"
if [[ -z "$LADDER_JSON" ]]; then
  LADDER_JSON=$("$PY" -c 'import json,sys; print(json.dumps({k:float(v) for k,v in (item.split("=") for item in sys.argv[1].split(","))}))' "$LADDER")
fi
mkdir -p "$OUT" "$LOG"
cd "$ROOT"
export PYTHONPATH="$SOURCE:$ROOT${PYTHONPATH:+:$PYTHONPATH}"

if nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | grep -q '[0-9]'; then
  echo "GPU compute process already exists; refusing to mix stale work into Phase 22R" >&2
  exit 20
fi

prior=(
  results/end_to_end/phase19b_untouched_sessions_v0.jsonl
  results/cross_model/phase19c_calibration_sessions_v0.jsonl
  results/cross_model/phase19c_heldout_sessions_v0.jsonl
  results/cross_model/phase20d_development_sessions_v0.jsonl
  results/cross_model/phase20d_heldout_sealed_sessions_v0.jsonl
  results/mistral/development_sessions_v0.jsonl
  results/mistral/heldout_sealed_sessions_v0.jsonl
  results/cross_model/llama_broad_generalization_r1/development_sessions_v0.jsonl
  results/cross_model/llama_broad_generalization_r1/heldout_sealed_sessions_v0.jsonl
  results/cross_model/llama_broad_generalization_r2/development_sessions_v0.jsonl
  results/cross_model/llama_broad_generalization_r2/heldout_sealed_sessions_v0.jsonl
)
prior_args=()
for path in "${prior[@]}"; do prior_args+=(--prior-sessions "$path"); done
"$PY" scripts/phase22r_prepare_llama_split.py \
  --full-pool results/workload/phase14d_full_pool_v2.jsonl \
  --phase19a-quality results/quality/phase19a_frozen_quality_v0.csv \
  "${prior_args[@]}" --development-per-family 5 --heldout-per-family 10 --selection-salt "$SELECTION_SALT" \
  --development-output "$DEV" --heldout-output "$HELD" --commitment-output "$SPLIT"

"$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action install
"$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action install
cleanup_hooks() {
  "$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action uninstall >/dev/null 2>&1 || true
  "$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action remove >/dev/null 2>&1 || true
}
trap cleanup_hooks EXIT

run_cell() {
  local partition=$1 label=$2 mode=$3 level=$4 sessions=$5 gpu=$6 port=$7 policy_hash=$8
  local dir output metrics pid log
  dir="$OUT/$partition"
  output="$dir/${label}.jsonl"; metrics="$dir/${label}_metrics.jsonl"
  pid="$LOG/${label}.pid"; log="$LOG/${label}_server.log"
  mkdir -p "$dir"; rm -f "$output" "$metrics" "$pid"
  (
    set -euo pipefail
    export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1
    export CONTRACTKV_PREFIX_METRICS_LOG="$metrics" CONTRACTKV_POLICY_HASH="$policy_hash"
    export CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000 CONTRACTKV_MAX_DEGRADATION=1000000000
    export EXTRA_VLLM_ARGS="--enable-prefix-caching"
    cleanup_server() { bash scripts/stop_vllm_server.sh --pid-path "$pid" --port "$port" || true; }
    trap cleanup_server EXIT
    bash scripts/run_vllm_server.sh --phase "$label" --model-path "$MODEL" --served-model-name llama31-8b \
      --port "$port" --gpu-ids "$gpu" --tensor-parallel-size 1 --dtype float16 \
      --max-model-len "$MAX_MODEL_LEN" --max-num-seqs 2 --gpu-memory-utilization .88 \
      --log-path "$log" --pid-path "$pid"
    command=("$PY" scripts/phase22_llama_broad_live.py --sessions "$sessions" \
      --base-url "http://127.0.0.1:$port/v1" --model llama31-8b --model-identity "$MODEL" \
      --mode "$mode" --level "$level" --layout-ladder "$LADDER" \
      --policy-hash "$policy_hash" --load-tier "$label" --concurrency 2 --turns 10 \
      --stable-word-limit 1500 --stable-pieces "$STABLE_PIECES" --max-tokens 96 --tool-slack-ms 6000 --slo-ms 1500 \
      --metrics-events "$metrics" --output "$output")
    if [[ "$mode" == frozen ]]; then command+=(--qualification-manifest "$MANIFEST"); fi
    "${command[@]}"
  )
}

run_pair() {
  local partition=$1 left_label=$2 left_mode=$3 left_level=$4 right_label=$5 right_mode=$6 right_level=$7 sessions=$8 hash=$9
  run_cell "$partition" "$left_label" "$left_mode" "$left_level" "$sessions" 0 $((8600 + RANDOM % 180)) "$hash" & p0=$!
  sleep 2
  run_cell "$partition" "$right_label" "$right_mode" "$right_level" "$sessions" 1 $((8820 + RANDOM % 180)) "$hash" & p1=$!
  failed=0; wait "$p0" || failed=1; wait "$p1" || failed=1
  [[ $failed -eq 0 ]] || return 31
}

if [[ "$RUN_SCOPE" == all || "$RUN_SCOPE" == development || "$RUN_SCOPE" == freeze ]]; then
  DEV_HASH="phase22r-development-ladder-v1"
  if [[ "$RUN_SCOPE" != freeze ]]; then
    run_pair development dev-L0 raw L0 dev-L1 level L1 "$DEV" "$DEV_HASH"
    run_pair development dev-L2 level L2 dev-L3 level L3 "$DEV" "$DEV_HASH"
  fi
  "$PY" scripts/phase22_llama_broad_analysis.py freeze --sessions "$DEV" \
    --cell "L0=$OUT/development/dev-L0.jsonl" --cell "L1=$OUT/development/dev-L1.jsonl" \
    --cell "L2=$OUT/development/dev-L2.jsonl" --cell "L3=$OUT/development/dev-L3.jsonl" \
    --model-identity "$MODEL" --minimum-development-sessions 5 --minimum-admitted-coverage "$MIN_COVERAGE" \
    --layout-ladder "$LADDER_JSON" --split-commitment "$SPLIT" --max-tokens 96 \
    --stable-word-limit 1500 --stable-pieces "$STABLE_PIECES" \
    --development-summary "$OUT/development_layout_summary_v0.csv" \
    --quality-output "$OUT/development_quality_v0.csv" --manifest "$MANIFEST"
  if [[ "$RUN_SCOPE" == development || "$RUN_SCOPE" == freeze ]]; then echo PHASE22R_DEVELOPMENT_COMPLETE; exit 0; fi
fi

if [[ ! -f "$MANIFEST" ]]; then echo "missing frozen qualification manifest" >&2; exit 40; fi
QUALIFIED=$("$PY" -c "import json;print(len(json.load(open('$MANIFEST'))['qualified_families']))")
if (( QUALIFIED < 3 )); then
  echo "development gate closed: only $QUALIFIED/5 families qualified; sealed heldout remains unopened" >&2
  exit 41
fi
HASH=$("$PY" -c "import json;print(json.load(open('$MANIFEST'))['qualification_hash'])")
for repeat in 1 2 3; do
  if (( repeat % 2 == 1 )); then
    run_pair "repeat$repeat" "r${repeat}-raw" raw L0 "r${repeat}-contract" frozen L0 "$HELD" "$HASH"
  else
    run_pair "repeat$repeat" "r${repeat}-contract" frozen L0 "r${repeat}-raw" raw L0 "$HELD" "$HASH"
  fi
done
pairs=()
for repeat in 1 2 3; do pairs+=(--pair "$repeat,$OUT/repeat$repeat/r${repeat}-raw.jsonl,$OUT/repeat$repeat/r${repeat}-contract.jsonl"); done
"$PY" scripts/phase22_llama_broad_analysis.py heldout --sessions "$HELD" --manifest "$MANIFEST" \
  "${pairs[@]}" --slo-ms 1500 --raw-summary "$OUT/heldout_scope_repeats_v0.csv" \
  --aggregate-summary "$OUT/heldout_scope_aggregate_v0.csv" \
  --quality-output "$OUT/heldout_quality_v0.csv" --level-output "$OUT/heldout_level_selection_v0.csv" \
  --gate-output "$OUT/heldout_gate_v0.json"
echo PHASE22R_LLAMA_BROAD_COMPLETE
