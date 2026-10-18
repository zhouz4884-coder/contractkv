#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"; PYTHON_BIN="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"; MODEL_PATH="${MODEL_PATH:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-8B}"; PORT="${PORT:-8020}"
cd "$ROOT"; mkdir -p logs/phase17r results/hard_systems; PID="logs/phase17r/qwen8b_refresh.pid"; rm -f "$PID"
export EXTRA_VLLM_ARGS="--enable-prefix-caching --max-num-batched-tokens 1024"; stop(){ [[ -f "$PID" ]] && kill "$(cat "$PID")" 2>/dev/null || true; }; trap stop EXIT
bash scripts/run_vllm_server.sh --phase phase17rrefresh --model-path "$MODEL_PATH" --served-model-name qwen3-8b --port "$PORT" --gpu-ids 0 --tensor-parallel-size 1 --dtype float16 --max-model-len 8192 --max-num-seqs 2 --gpu-memory-utilization 0.88 --log-path logs/phase17r/qwen8b_refresh.log --pid-path "$PID"
"$PYTHON_BIN" scripts/phase17r_unsafe_label_refresh.py --base-url "http://127.0.0.1:${PORT}/v1" --model qwen3-8b --model-path "$MODEL_PATH" --policy results/hard_systems/phase17r_frozen_policy_manifest_v0.json --full-pool results/workload/phase14d_full_pool_v2.jsonl --jobs results/end_to_end/phase14r_quality_jobs_v5.jsonl --labels results/end_to_end/phase14r_quality_labels_v5.csv --output results/hard_systems/phase17r_unsafe_label_refresh_v0.csv
stop; trap - EXIT
