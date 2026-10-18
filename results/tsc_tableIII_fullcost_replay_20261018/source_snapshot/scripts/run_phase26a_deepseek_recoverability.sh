#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
SOURCE="${SOURCE_VLLM:-$ROOT/third_party/vllm-contractkv-phase19c}"
DEV="$ROOT/results/cross_model/llama_broad_generalization_r3/development_sessions_v0.jsonl"
BASE="$ROOT/results/cross_model/deepseek_phase26_recoverability"
PHASE25="$ROOT/results/cross_model/deepseek_v2_lite_pair"
PROTOCOL="$ROOT/configs/phase26_deepseek_recoverability_protocol_v0.json"
LOG_BASE="$ROOT/logs/phase26_deepseek_recoverability"
SCHEDULER="$SOURCE/vllm/v1/core/sched/scheduler.py"
PORT="${PHASE26_PORT:-8960}"

cd "$ROOT"
mkdir -p "$BASE" "$LOG_BASE"
export PYTHONPATH="$SOURCE:$ROOT${PYTHONPATH:+:$PYTHONPATH}"

remove_hooks() {
  "$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action uninstall >/dev/null 2>&1 || true
  "$PY" scripts/install_vllm_v1_phase17_hook.py --scheduler "$SCHEDULER" --action remove >/dev/null 2>&1 || true
  "$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action remove >/dev/null 2>&1 || true
}

stop_server() {
  local pid_path=$1
  bash scripts/stop_vllm_server.sh --pid-path "$pid_path" --port "$PORT" >/dev/null 2>&1 || true
}

cleanup() {
  for pid_path in "$LOG_BASE"/*.pid; do
    [[ -e "$pid_path" ]] && stop_server "$pid_path"
  done
  remove_hooks
}
trap cleanup EXIT

for key in chat coder; do
  if [[ "$key" == "chat" ]]; then
    model_path="/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/DeepSeek-V2-Lite-Chat"
    served_model="deepseek-v2-lite-chat"
  else
    model_path="/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/DeepSeek-Coder-V2-Lite-Instruct"
    served_model="deepseek-coder-v2-lite-instruct"
  fi
  output="$BASE/$key"
  log="$LOG_BASE/${key}_server.log"
  pid_path="$LOG_BASE/${key}_server.pid"
  mkdir -p "$output"
  remove_hooks
  export EXTRA_VLLM_ARGS="--enable-prefix-caching --trust-remote-code"
  bash scripts/run_vllm_server.sh --phase "phase26a-${key}-recoverability" \
    --model-path "$model_path" --served-model-name "$served_model" --port "$PORT" \
    --gpu-ids "0,1" --tensor-parallel-size 2 --dtype bfloat16 --max-model-len 16384 \
    --max-num-seqs 2 --gpu-memory-utilization .70 --log-path "$log" --pid-path "$pid_path"
  "$PY" scripts/phase26a_recoverability_audit.py \
    --sessions "$DEV" --diagnostics "$PHASE25/$key/certificate_diagnostic_v0.jsonl" \
    --protocol "$PROTOCOL" --base-url "http://127.0.0.1:$PORT/v1" \
    --model "$served_model" --model-path "$model_path" --model-key "$key" \
    --output-dir "$output" --resume
  stop_server "$pid_path"
done

echo PHASE26A_DEEPSEEK_RECOVERABILITY_COMPLETE
