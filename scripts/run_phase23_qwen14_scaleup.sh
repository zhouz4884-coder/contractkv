#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
MODEL="${MODEL_PATH:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-14B}"
SOURCE="${SOURCE_VLLM:-$ROOT/third_party/vllm-contractkv-phase19c}"
OUT="$ROOT/results/scale_up/qwen3_14b_tp2_v0"
LOG="$ROOT/logs/qwen3_14b_tp2_v0"
SESSIONS="$OUT/frozen_sessions_v0.jsonl"
COMMITMENT="$OUT/split_commitment_v0.json"
POLICY_MANIFEST="$OUT/policy_transfer_manifest_v0.json"
POLICY_HASH="55e10dc4f54daf428b382a35fe8a8feeded5b4b3f34752f36f45c8f825df1ee4"
SCHEDULER="$SOURCE/vllm/v1/core/sched/scheduler.py"
mkdir -p "$OUT" "$LOG"
cd "$ROOT"
export PYTHONPATH="$SOURCE:$ROOT${PYTHONPATH:+:$PYTHONPATH}"

if nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | grep -q '[0-9]'; then
  echo "GPU compute process already exists; refusing to mix stale work into Phase 23" >&2
  exit 20
fi

for file in config.json tokenizer.json tokenizer_config.json model.safetensors.index.json; do
  [[ -s "$MODEL/$file" ]] || { echo "incomplete Qwen3-14B: missing $file" >&2; exit 21; }
done
[[ $(find "$MODEL" -maxdepth 1 -name 'model-*.safetensors' | wc -l) -eq 8 ]] || {
  echo "incomplete Qwen3-14B: expected 8 shards" >&2; exit 22;
}

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
  results/cross_model/llama_broad_generalization_r3/development_sessions_v0.jsonl
  results/cross_model/llama_broad_generalization_r3/heldout_sealed_sessions_v0.jsonl
)
prior_args=()
for path in "${prior[@]}"; do [[ -f "$path" ]] && prior_args+=(--prior-sessions "$path"); done
"$PY" scripts/phase23_prepare_qwen14_scaleup.py \
  --full-pool results/workload/phase14d_full_pool_v2.jsonl \
  --phase19a-quality results/quality/phase19a_frozen_quality_v0.csv \
  "${prior_args[@]}" --sessions-per-family 5 --selection-salt qwen3-14b-tp2-scaleup-v0 \
  --model-identity "$MODEL" --source-policy-hash "$POLICY_HASH" \
  --sessions-output "$SESSIONS" --commitment-output "$COMMITMENT" \
  --policy-manifest-output "$POLICY_MANIFEST"
QUALIFICATION_HASH=$($PY -c "import json;print(json.load(open('$POLICY_MANIFEST'))['qualification_hash'])")

"$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action install
"$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action install
cleanup_hooks() {
  "$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action uninstall >/dev/null 2>&1 || true
  "$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action remove >/dev/null 2>&1 || true
}
trap cleanup_hooks EXIT

run_cell() {
  local label=$1 policy=$2 port=$3
  local dir output metrics pid log
  dir="$OUT/${label%%-*}"; mkdir -p "$dir"
  output="$dir/${label}.jsonl"; metrics="$dir/${label}_metrics.jsonl"
  pid="$LOG/${label}.pid"; log="$LOG/${label}_server.log"
  rm -f "$output" "$metrics" "$pid"
  (
    set -euo pipefail
    export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1
    export CONTRACTKV_PREFIX_METRICS_LOG="$metrics" CONTRACTKV_POLICY_HASH="$POLICY_HASH"
    export CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000 CONTRACTKV_MAX_DEGRADATION=1000000000
    export EXTRA_VLLM_ARGS="--enable-prefix-caching"
    cleanup_server() { bash scripts/stop_vllm_server.sh --pid-path "$pid" --port "$port" || true; }
    trap cleanup_server EXIT
    bash scripts/run_vllm_server.sh --phase "$label" --model-path "$MODEL" \
      --served-model-name qwen3-14b --port "$port" --gpu-ids "0,1" --tensor-parallel-size 2 \
      --dtype float16 --max-model-len 8192 --max-num-seqs 2 --gpu-memory-utilization .88 \
      --log-path "$log" --pid-path "$pid"
    "$PY" scripts/phase19b_end_to_end_live.py --sessions "$SESSIONS" \
      --base-url "http://127.0.0.1:$port/v1" --model qwen3-14b --model-identity "$MODEL" \
      --policy "$policy" --policy-hash "$POLICY_HASH" --qualification-hash "$QUALIFICATION_HASH" \
      --load-tier "$label" --concurrency 2 --turns 10 --stable-word-limit 2600 --max-tokens 96 \
      --tool-slack-ms 2000 --slo-ms 2000 --timeout 600 --metrics-events "$metrics" --output "$output"
  )
}

for repeat in 1 2 3; do
  if (( repeat % 2 == 1 )); then order=(raw contract); else order=(contract raw); fi
  for kind in "${order[@]}"; do
    if [[ "$kind" == raw ]]; then
      policy=raw-order; port=$((9100 + repeat * 10 + 1))
    else
      policy=contractkv-full; port=$((9100 + repeat * 10 + 2))
    fi
    run_cell "r${repeat}-${kind}" "$policy" "$port"
  done
done

pairs=()
for repeat in 1 2 3; do
  pairs+=(--pair "$repeat,$OUT/r$repeat/r${repeat}-raw.jsonl,$OUT/r$repeat/r${repeat}-contract.jsonl")
done
"$PY" scripts/phase23_qwen14_scaleup_analysis.py --sessions "$SESSIONS" "${pairs[@]}" --slo-ms 2000 \
  --raw-output "$OUT/paired_raw_v0.jsonl" --repeat-output "$OUT/repeat_summary_v0.csv" \
  --aggregate-output "$OUT/aggregate_summary_v0.csv" --quality-output "$OUT/quality_pairs_v0.csv" \
  --family-output "$OUT/family_quality_v0.csv" --gate-output "$OUT/gate_v0.json"
echo PHASE23_QWEN14_SCALEUP_COMPLETE
