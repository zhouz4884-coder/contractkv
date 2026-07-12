#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PYTHON_BIN="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
MODEL_PATH="${MODEL_PATH:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-8B}"
PORT=8017
PID=logs/phase17/phase17_calibration_server.pid
cd "$ROOT"; mkdir -p logs/phase17 results/hard_systems
rm -f "$PID"
export EXTRA_VLLM_ARGS="--enable-chunked-prefill --max-num-batched-tokens 1024"
stop(){ [[ -f "$PID" ]] && kill "$(cat "$PID")" 2>/dev/null || true; sleep 3; }
trap stop EXIT
bash scripts/run_vllm_server.sh --phase phase17cal --model-path "$MODEL_PATH" --served-model-name qwen3-8b \
  --port "$PORT" --gpu-ids 0 --tensor-parallel-size 1 --dtype float16 --max-model-len 8192 \
  --max-num-seqs 2 --gpu-memory-utilization 0.88 --log-path logs/phase17/phase17_calibration_server.log --pid-path "$PID"
"$PYTHON_BIN" scripts/phase17_calibration_rerun.py --base-url "http://127.0.0.1:${PORT}/v1" \
  --model qwen3-8b --model-path "$MODEL_PATH" \
  --raw-output results/hard_systems/phase17_calibration_raw_attestations_v0.jsonl \
  --candidate-output results/hard_systems/phase17_calibration_candidate_margins_v2.jsonl \
  --retry-all
"$PYTHON_BIN" scripts/phase17_calibrate_thresholds.py \
  --input results/hard_systems/phase17_calibration_candidate_margins_v2.csv \
  --threshold-output results/hard_systems/phase17_frozen_thresholds_v0.json \
  --summary-output results/hard_systems/phase17_threshold_calibration_summary_v0.csv
stop; trap - EXIT
