#!/usr/bin/env bash
# Paper-grade finite shared-context capacity scan: fresh server per point.
set -euo pipefail

ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PYTHON_BIN="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
MODEL_PATH="${MODEL_PATH:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-8B}"
OUT="${OUT:-$ROOT/results/hard_systems/phase15b_shared_cells}"
GPU_IDS="${GPU_IDS:-0}"
PORT="${PORT:-8001}"
SEED="${SEED:-15101}"
CAP_RATES="${CAP_RATES:-24 32 40}"
RAW_RATES="${RAW_RATES:-1 2}"

cd "$ROOT"
mkdir -p "$OUT"
pid_path=""
cleanup() { [[ -z "$pid_path" ]] || bash scripts/stop_vllm_server.sh --pid-path "$pid_path" --port "$PORT" || true; }
trap cleanup EXIT

run_point() {
  local policy="$1" rate="$2" seconds="$3"
  local rate_tag="${rate/./p}"
  local cell="phase15b_shared_s${SEED}_${policy}_r${rate_tag}"
  local metrics="$OUT/${cell}_metrics.jsonl" log="$OUT/${cell}_server.log"
  pid_path="$OUT/${cell}.pid"
  local raw="$OUT/${cell}_raw.csv" summary="$OUT/${cell}_summary.csv"
  [[ -s "$summary" ]] && { echo "SKIP completed cell=$cell"; return; }
  rm -f "$metrics" "$log" "$pid_path" "$raw" "$summary"
  export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_METRICS_LOG="$metrics"
  export EXTRA_VLLM_ARGS="--enable-prefix-caching"
  bash scripts/run_vllm_server.sh --phase phase15b-shared-capacity --model-path "$MODEL_PATH" --served-model-name qwen3-8b \
    --port "$PORT" --gpu-ids "$GPU_IDS" --tensor-parallel-size 1 --dtype float16 --max-model-len 8192 --max-num-seqs 8 \
    --gpu-memory-utilization 0.88 --log-path "$log" --pid-path "$pid_path"
  "$PYTHON_BIN" scripts/phase14d_open_loop_capacity.py --policy "$policy" --arrival-rate-rps "$rate" \
    --measurement-seconds "$seconds" --drain-seconds 90 --shared-target-tokens 2048 --tokenizer "$MODEL_PATH" \
    --metrics-events "$metrics" --slo-ttft-ms 5000 --seed "$SEED" --min-completed 200 --min-second-half-samples 100 \
    --cell-id "$cell" --raw-output "$raw" --summary-output "$summary"
  bash scripts/stop_vllm_server.sh --pid-path "$pid_path" --port "$PORT" || true
  pid_path=""
}

for rate in $RAW_RATES; do
  case "$rate" in
    0.5) seconds=480 ;;
    0.75) seconds=280 ;;
    1) seconds=220 ;;
    2) seconds=110 ;;
    *) seconds=220 ;;
  esac
  run_point raw-order "$rate" "$seconds"
done
for rate in $CAP_RATES; do
  run_point contractkv-caposc "$rate" 15
done
