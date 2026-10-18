#!/usr/bin/env bash
# Run one fresh vLLM process per Phase 15A natural mixed-agent cell.
# Policy/cell identity is never inserted into the request prompt.
set -euo pipefail

ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PYTHON_BIN="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
MODEL_PATH="${MODEL_PATH:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-8B}"
FULL_POOL="${FULL_POOL:-$ROOT/results/workload/phase14d_full_pool_v2.jsonl}"
QC_MODEL="${QC_MODEL:-$ROOT/results/end_to_end/phase14r_qc_v2_model_v5.json}"
TOKENIZER="${TOKENIZER:-$MODEL_PATH}"
OUT="${OUT:-$ROOT/results/hard_systems/phase15a_natural_cells}"
GPU_IDS="${GPU_IDS:-0}"
PORT="${PORT:-8001}"
SEEDS="${SEEDS:-15001 15002 15003}"
CONCURRENCIES="${CONCURRENCIES:-1 4}"
POLICIES="${POLICIES:-vllm-raw-order static-posc contractkv-caposc}"
SKIP_SUMMARY="${SKIP_SUMMARY:-0}"

cd "$ROOT"
mkdir -p "$OUT"
pid_path=""
cleanup() {
  if [[ -n "$pid_path" ]]; then
    bash scripts/stop_vllm_server.sh --pid-path "$pid_path" --port "$PORT" || true
  fi
}
trap cleanup EXIT

policy_order() {
  case "$1" in
    *1) echo "vllm-raw-order static-posc contractkv-caposc" ;;
    *2) echo "static-posc contractkv-caposc vllm-raw-order" ;;
    *) echo "contractkv-caposc vllm-raw-order static-posc" ;;
  esac
}

for seed in $SEEDS; do
  for concurrency in $CONCURRENCIES; do
    for policy in $(policy_order "$seed"); do
      [[ " $POLICIES " == *" $policy "* ]] || continue
      cell="phase15a_natural_s${seed}_c${concurrency}_${policy}"
      metrics="$OUT/${cell}_metrics.jsonl"
      log="$OUT/${cell}_server.log"
      pid_path="$OUT/${cell}.pid"
      raw="$OUT/${cell}_raw.csv"
      summary="$OUT/${cell}_summary.csv"
      if [[ -s "$raw" && -s "$summary" ]]; then
        echo "SKIP completed cell=$cell"
        continue
      fi
      rm -f "$metrics" "$log" "$pid_path" "$raw" "$summary"
      export CONTRACTKV_PREFIX_METRICS=1
      export CONTRACTKV_PREFIX_METRICS_LOG="$metrics"
      export CONTRACTKV_PREFIX_CONCURRENT_SNAPSHOTS=1
      export CONTRACTKV_RESIDENCY_VALIDATOR=1
      export CONTRACTKV_RESIDENCY_LOG="$OUT/${cell}_residency.jsonl"
      export EXTRA_VLLM_ARGS="--enable-prefix-caching"
      bash scripts/run_vllm_server.sh \
        --phase phase15a-fair-natural --model-path "$MODEL_PATH" --served-model-name qwen3-8b \
        --port "$PORT" --gpu-ids "$GPU_IDS" --tensor-parallel-size 1 --dtype float16 \
        --max-model-len 8192 --max-num-seqs 2 --gpu-memory-utilization 0.88 \
        --log-path "$log" --pid-path "$pid_path"
      "$PYTHON_BIN" scripts/phase14d_live_mixed_serving.py \
        --full-pool "$FULL_POOL" --qc-model "$QC_MODEL" --tokenizer "$TOKENIZER" \
        --base-url "http://127.0.0.1:${PORT}/v1" --model qwen3-8b \
        --sessions-per-family 3 --turns 5 --arrival-modes burst --policies "$policy" \
        --concurrencies "$concurrency" --slo-buckets-ms 1000,2000,3000,5000 \
        --seed "$seed" --metrics-events "$metrics" --raw-output "$raw" --summary-output "$summary"
      bash scripts/stop_vllm_server.sh --pid-path "$pid_path" --port "$PORT" || true
      pid_path=""
    done
  done
done

if [[ "$SKIP_SUMMARY" != "1" ]]; then
  "$PYTHON_BIN" scripts/summarize_phase15a_fair_replication.py \
    --cell-dir "$OUT" \
    --raw-output "$ROOT/results/hard_systems/phase15a_natural_fair_raw_v0.csv" \
    --summary-output "$ROOT/results/hard_systems/phase15a_natural_fair_summary_v0.csv"
fi
