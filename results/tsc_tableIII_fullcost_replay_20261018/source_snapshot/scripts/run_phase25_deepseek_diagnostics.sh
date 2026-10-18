#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
SOURCE="${SOURCE_VLLM:-$ROOT/third_party/vllm-contractkv-phase19c}"
DEV="$ROOT/results/cross_model/llama_broad_generalization_r3/development_sessions_v0.jsonl"
BASE="$ROOT/results/cross_model/deepseek_v2_lite_pair"
LOG_BASE="$ROOT/logs/phase25_deepseek_v2_lite_pair/diagnostics"
SCHEDULER="$SOURCE/vllm/v1/core/sched/scheduler.py"
PORT="${PHASE25_DIAGNOSTIC_PORT:-8950}"

cd "$ROOT"
mkdir -p "$LOG_BASE"
export PYTHONPATH="$SOURCE:$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export CONTRACTKV_VERIFIER_CODE_COMMIT="phase25-deepseek-pair-frozen-protocol-v1"
export CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000
export CONTRACTKV_MAX_DEGRADATION=1000000000

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
  output="$BASE/$key/certificate_diagnostic_v0.jsonl"
  log="$LOG_BASE/${key}_server.log"
  pid_path="$LOG_BASE/${key}_server.pid"
  rm -f "$output" "$pid_path"
  remove_hooks
  "$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action install
  "$PY" -m py_compile "$SCHEDULER"
  export EXTRA_VLLM_ARGS="--enable-prefix-caching --trust-remote-code"
  bash scripts/run_vllm_server.sh --phase "phase25-${key}-certificate-diagnostic" \
    --model-path "$model_path" --served-model-name "$served_model" --port "$PORT" \
    --gpu-ids "0,1" --tensor-parallel-size 2 --dtype bfloat16 --max-model-len 8192 \
    --max-num-seqs 2 --gpu-memory-utilization .90 --log-path "$log" --pid-path "$pid_path"
  "$PY" scripts/phase25_deepseek_certificate_diagnostic.py \
    --sessions "$DEV" --base-url "http://127.0.0.1:$PORT/v1" --model "$served_model" \
    --model-identity "$model_path" --policy-hash "phase25-${key}-development-diagnostic-v1" \
    --load-tier "phase25-${key}-development-diagnostic" --stable-word-limit 1150 \
    --max-tokens 128 --output "$output"
  stop_server "$pid_path"
  remove_hooks
done

"$PY" scripts/phase25_deepseek_pair_analysis.py diagnostic-summary \
  --chat "$BASE/chat/certificate_diagnostic_v0.jsonl" \
  --coder "$BASE/coder/certificate_diagnostic_v0.jsonl" \
  --output "$BASE/certificate_failure_summary_v0.csv" \
  --margin-output "$BASE/certificate_margin_summary_v0.csv"

echo PHASE25_DEEPSEEK_DIAGNOSTICS_COMPLETE
