#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PYTHON_BIN="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
MODEL_PATH="${MODEL_PATH:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-8B}"
PORT="${PORT:-8025}"
SOURCE_VLLM="${SOURCE_VLLM:-$ROOT/third_party/vllm-contractkv}"
QUALITY_DIR="$ROOT/results/quality"
LOG_DIR="$ROOT/logs/phase19a"

mkdir -p "$QUALITY_DIR" "$LOG_DIR"
cd "$ROOT"
export PYTHONPATH="$SOURCE_VLLM:$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export HF_HOME="/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/datasets/hf_cache"
export HF_DATASETS_CACHE="$HF_HOME/datasets"
export VLLM_USE_V1=1

if ss -ltn 2>/dev/null | grep -q ":${PORT} "; then
  echo "port ${PORT} is already occupied" >&2
  exit 2
fi

CUDA_VISIBLE_DEVICES=0 "$PYTHON_BIN" -m vllm.entrypoints.openai.api_server \
  --model "$MODEL_PATH" --served-model-name qwen3-8b --dtype float16 \
  --tensor-parallel-size 1 --gpu-memory-utilization 0.88 \
  --max-model-len 16384 --max-num-seqs 2 --port "$PORT" \
  >"$LOG_DIR/server.log" 2>&1 &
SERVER_PID=$!

cleanup() {
  kill "$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT

for _ in $(seq 1 240); do
  if curl -fsS "http://127.0.0.1:${PORT}/v1/models" >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    tail -n 120 "$LOG_DIR/server.log" >&2
    exit 3
  fi
  sleep 2
done
curl -fsS "http://127.0.0.1:${PORT}/v1/models" >/dev/null

"$PYTHON_BIN" scripts/phase19a_rebuild_quality_pool.py \
  --base-url "http://127.0.0.1:${PORT}/v1" \
  --model qwen3-8b --model-path "$MODEL_PATH" \
  --policy results/hard_systems/phase17r_frozen_policy_manifest_v0.json \
  --full-pool results/workload/phase14d_full_pool_v2.jsonl \
  --jobs results/end_to_end/phase14r_quality_jobs_v5.jsonl \
  --labels results/end_to_end/phase14r_quality_labels_v5.csv \
  --features results/end_to_end/phase14r_qc_candidate_features_v5.csv \
  --raw-cache "$QUALITY_DIR/phase19a_raw_generation_cache_v0.jsonl" \
  --candidate-cache "$QUALITY_DIR/phase19a_candidate_generation_cache_v0.jsonl" \
  --output "$QUALITY_DIR/phase19a_frozen_quality_v0.csv" \
  --provenance-output "$QUALITY_DIR/phase19a_frozen_provenance_manifest_v0.json" \
  --workers 2 --retries 2 --retry-errors \
  2>&1 | tee "$LOG_DIR/rebuild.log"

"$PYTHON_BIN" scripts/phase19a_audit_provenance.py \
  --quality "$QUALITY_DIR/phase19a_frozen_quality_v0.csv" \
  --legacy-labels results/end_to_end/phase14r_quality_labels_v5.csv \
  --jobs results/end_to_end/phase14r_quality_jobs_v5.jsonl \
  --output "$QUALITY_DIR/phase19a_provenance_audit_v0.csv" \
  --summary-output "$QUALITY_DIR/phase19a_provenance_audit_summary_v0.json"

"$PYTHON_BIN" scripts/phase19a_freeze_quality_summary.py \
  --quality "$QUALITY_DIR/phase19a_frozen_quality_v0.csv" \
  --audit-summary "$QUALITY_DIR/phase19a_provenance_audit_summary_v0.json" \
  --output "$QUALITY_DIR/phase19a_frozen_quality_summary_v0.csv" \
  --json-output "$QUALITY_DIR/phase19a_frozen_quality_summary_v0.json"

echo "PHASE19A_COMPLETE"
