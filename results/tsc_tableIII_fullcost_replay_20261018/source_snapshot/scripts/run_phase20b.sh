#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
MODEL_PATH="${MODEL_PATH:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Llama-3.1-8B-Instruct}"
SOURCE_VLLM="${SOURCE_VLLM:-$ROOT/third_party/vllm-contractkv-phase19c}"
PORT="${PORT:-8050}"
GPU="${GPU:-0}"
PID="$ROOT/logs/phase20/phase20b_server.pid"

cd "$ROOT"
mkdir -p logs/phase20 results/cross_model
export PYTHONPATH="$SOURCE_VLLM:$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export EXTRA_VLLM_ARGS="--enable-prefix-caching"

cleanup() {
  bash scripts/stop_vllm_server.sh --pid-path "$PID" --port "$PORT" || true
}
trap cleanup EXIT

bash scripts/run_vllm_server.sh \
  --phase phase20b --model-path "$MODEL_PATH" --served-model-name llama31-8b \
  --port "$PORT" --gpu-ids "$GPU" --tensor-parallel-size 1 --dtype float16 \
  --max-model-len 8192 --max-num-seqs 2 --gpu-memory-utilization .88 \
  --log-path logs/phase20/phase20b_server.log --pid-path "$PID"

"$PY" scripts/phase20b_llama_rejection_audit.py \
  --base-url "http://127.0.0.1:$PORT/v1" --model llama31-8b \
  --labels results/cross_model/phase19c_heldout_quality_labels_v0.csv \
  --sessions results/cross_model/phase19c_heldout_sessions_v0.jsonl \
  --output results/cross_model/phase20b_llama_rejection_audit_v0.jsonl \
  --summary-output results/cross_model/phase20b_llama_rejection_summary_v0.json

"$PY" scripts/phase20b_summarize_taxonomy.py \
  --input results/cross_model/phase20b_llama_rejection_audit_v0.jsonl \
  --output results/cross_model/phase20b_llama_rejection_taxonomy_v0.csv

cleanup
trap - EXIT
cat results/cross_model/phase20b_llama_rejection_summary_v0.json
