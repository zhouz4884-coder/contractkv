#!/usr/bin/env bash
# Fresh-process Phase 15A replication for real concurrent physical KV sharing.
set -euo pipefail

ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PYTHON_BIN="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
MODEL_PATH="${MODEL_PATH:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-8B}"
OUT="${OUT:-$ROOT/results/hard_systems/phase15a_physical_cells}"
GPU_IDS="${GPU_IDS:-0}"
PORT="${PORT:-8001}"
SEEDS="${SEEDS:-15001 15002 15003}"
CONFIGS="${CONFIGS:-4096:16 6144:20}"
POLICIES="${POLICIES:-raw-order static-posc contractkv-caposc}"
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
    *1) echo "raw-order static-posc contractkv-caposc" ;;
    *2) echo "static-posc contractkv-caposc raw-order" ;;
    *) echo "contractkv-caposc raw-order static-posc" ;;
  esac
}

for seed in $SEEDS; do
  for config in $CONFIGS; do
    tokens="${config%%:*}"
    sessions="${config##*:}"
    for policy in $(policy_order "$seed"); do
      [[ " $POLICIES " == *" $policy "* ]] || continue
      cell="phase15a_physical_s${seed}_t${tokens}_n${sessions}_${policy}"
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
        --phase phase15a-fair-physical --model-path "$MODEL_PATH" --served-model-name qwen3-8b \
        --port "$PORT" --gpu-ids "$GPU_IDS" --tensor-parallel-size 1 --dtype float16 \
        --max-model-len 8192 --max-num-seqs "$sessions" --gpu-memory-utilization 0.88 \
        --log-path "$log" --pid-path "$pid_path"
      "$PYTHON_BIN" scripts/phase14m_physical_dedup.py \
        --experiment warm --policy "$policy" --shared-target-tokens "$tokens" --sessions "$sessions" \
        --tokenizer "$MODEL_PATH" --metrics-events "$metrics" --base-url "http://127.0.0.1:${PORT}/v1" \
        --model qwen3-8b --max-tokens 16 --cell-id "$cell" --raw-output "$raw" --summary-output "$summary"
      bash scripts/stop_vllm_server.sh --pid-path "$pid_path" --port "$PORT" || true
      pid_path=""
    done
  done
done

if [[ "$SKIP_SUMMARY" != "1" ]]; then
  "$PYTHON_BIN" scripts/summarize_phase15a_physical_replication.py \
    --cell-dir "$OUT" \
    --raw-output "$ROOT/results/hard_systems/phase15a_physical_fair_raw_v0.csv" \
    --summary-output "$ROOT/results/hard_systems/phase15a_physical_fair_summary_v0.csv"
fi
