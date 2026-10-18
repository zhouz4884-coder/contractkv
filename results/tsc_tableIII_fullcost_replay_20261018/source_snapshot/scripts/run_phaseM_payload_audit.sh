#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
MODEL_PATH="${MODEL_PATH:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Mistral-7B-Instruct-v0.3}"
SOURCE_VLLM="${SOURCE_VLLM:-$ROOT/third_party/vllm-contractkv-phase19c}"
PORT=8061; PID="$ROOT/logs/mistral/payload-audit.pid"; LOG="$ROOT/logs/mistral/payload-audit.log"
cd "$ROOT"; export PYTHONPATH="$SOURCE_VLLM:$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export EXTRA_VLLM_ARGS="--enable-prefix-caching"
cleanup(){ bash scripts/stop_vllm_server.sh --pid-path "$PID" --port "$PORT" || true; }
trap cleanup EXIT
bash scripts/run_vllm_server.sh --phase mistral-payload-audit --model-path "$MODEL_PATH" \
  --served-model-name mistral7b --port "$PORT" --gpu-ids 0 --tensor-parallel-size 1 \
  --dtype float16 --max-model-len 8192 --max-num-seqs 1 --gpu-memory-utilization .88 \
  --log-path "$LOG" --pid-path "$PID"
"$PY" scripts/phaseM_logprob_payload_audit.py --sessions results/mistral/development_sessions_v0.jsonl \
  --base-url "http://127.0.0.1:$PORT/v1" --model mistral7b --session-id mistral-hotpotqa-152 \
  --output results/mistral/logprob_payload_audit_v0.json
echo MISTRAL_LOGPROB_PAYLOAD_AUDIT_COMPLETE
