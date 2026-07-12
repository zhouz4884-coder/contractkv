#!/usr/bin/env bash
set -euo pipefail
ROOT="/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv"
PYTHON_BIN="/home/user/miniconda3/envs/contractkv-cu128/bin/python"
MODEL_PATH="/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-8B"
PID="logs/phase17/phase17_debug_server.pid"; cd "$ROOT"; rm -f "$PID"
export EXTRA_VLLM_ARGS="--enable-chunked-prefill --max-num-batched-tokens 1024"
stop(){ [[ -f "$PID" ]] && kill "$(cat "$PID")" 2>/dev/null || true; sleep 2; }; trap stop EXIT
bash scripts/run_vllm_server.sh --phase phase17debug --model-path "$MODEL_PATH" --served-model-name qwen3-8b --port 8017 --gpu-ids 0 --tensor-parallel-size 1 --dtype float16 --max-model-len 8192 --max-num-seqs 1 --gpu-memory-utilization 0.88 --log-path logs/phase17/phase17_debug_server.log --pid-path "$PID"
"$PYTHON_BIN" scripts/phase17_prompt_logprob_debug.py --base-url http://127.0.0.1:8017/v1 --model qwen3-8b --model-path "$MODEL_PATH" --raw results/hard_systems/phase17_calibration_raw_attestations_v0.jsonl --output results/hard_systems/phase17_prompt_logprob_debug_v0.json
stop; trap - EXIT
