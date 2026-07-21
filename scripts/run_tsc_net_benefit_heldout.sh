#!/usr/bin/env bash
# Frozen-net-benefit gate validation on points withheld from threshold selection.
set -euo pipefail

ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PYTHON_BIN="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
SOURCE="${VLLM_SOURCE:-$ROOT/third_party/vllm-contractkv-phase19c}"
MODEL_PATH="${MODEL_PATH:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-8B}"
PORT="${PORT:-8031}"
OUT="$ROOT/results/tsc_service/economics/heldout_gate_v1"
LOG="$ROOT/logs/tsc_service/economics"
PID="$LOG/heldout_gate_server.pid"

mkdir -p "$OUT" "$LOG"
cd "$ROOT"
export PYTHONPATH="$SOURCE:$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export CONTRACTKV_PREFIX_METRICS=1
export CONTRACTKV_PREFIX_INITIAL_ONLY=1
export CONTRACTKV_PREFIX_METRICS_LOG="$OUT/prefix_metrics.jsonl"
export EXTRA_VLLM_ARGS="--enable-prefix-caching"

cleanup() {
  bash scripts/stop_vllm_server.sh --pid-path "$PID" --port "$PORT" || true
}
trap cleanup EXIT

bash scripts/run_vllm_server.sh \
  --phase tsc-economics-heldout-gate-v1 --model-path "$MODEL_PATH" \
  --served-model-name qwen3-8b --port "$PORT" --gpu-ids 0 \
  --tensor-parallel-size 1 --dtype float16 --max-model-len 8192 \
  --max-num-seqs 4 --gpu-memory-utilization .88 \
  --log-path "$LOG/heldout_gate_server.log" --pid-path "$PID"

"$PYTHON_BIN" scripts/tsc_verification_economics_live.py \
  --tokenizer "$MODEL_PATH" --model-identity Qwen3-8B \
  --base-url "http://127.0.0.1:$PORT/v1" --model qwen3-8b \
  --policy-hash tsc-net-benefit-gate-v1 --load-tier sealed-heldout-gate-v1 \
  --raw-output "$OUT/raw.csv" --contour-output "$OUT/contour.csv" \
  --boundary-points-json configs/tsc_net_benefit_heldout_points_v1.json
