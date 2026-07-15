#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
SOURCE="${SOURCE_VLLM:-$ROOT/third_party/vllm-contractkv-phase19c}"
MODEL="/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/DeepSeek-Coder-V2-Lite-Instruct"
BASE="$ROOT/results/cross_model/deepseek_phase26_recoverability"
HELD="$BASE/sealed/heldout_sealed_sessions_v0.jsonl"
MANIFEST="$BASE/coder/typed_qualification_manifest_v0.json"
BUDGETS="$BASE/coder/frozen_task_output_budgets_v0.json"
LOG_BASE="$ROOT/logs/phase26_deepseek_coder_heldout"
SCHEDULER="$SOURCE/vllm/v1/core/sched/scheduler.py"
PORT="${PHASE26D_PORT:-8965}"

cd "$ROOT"
mkdir -p "$BASE/heldout" "$LOG_BASE"
export PYTHONPATH="$SOURCE:$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export VLLM_SERVER_DEV_MODE=1

remove_hooks() {
  "$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action uninstall >/dev/null 2>&1 || true
  "$PY" scripts/install_vllm_v1_phase17_hook.py --scheduler "$SCHEDULER" --action remove >/dev/null 2>&1 || true
  "$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action remove >/dev/null 2>&1 || true
}
cleanup() {
  bash scripts/stop_vllm_server.sh --pid-path "$LOG_BASE/current.pid" --port "$PORT" >/dev/null 2>&1 || true
  remove_hooks
}
trap cleanup EXIT
remove_hooks
"$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action install
"$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action install
"$PY" -m py_compile "$SCHEDULER"

HASH=$("$PY" -c "import json; print(json.load(open('$MANIFEST'))['qualification_hash'])")
for repeat in 1 2 3; do
  if (( repeat % 2 == 1 )); then modes=(raw contract); else modes=(contract raw); fi
  for mode in "${modes[@]}"; do
    label="r${repeat}-${mode}"
    output="$BASE/heldout/${label}.jsonl"
    metrics="$BASE/heldout/${label}_metrics.jsonl"
    log="$LOG_BASE/${label}_server.log"
    if [[ -f "$output" ]] && [[ "$(wc -l < "$output")" -eq 500 ]]; then
      echo "SKIP_COMPLETE $label $output"
      continue
    fi
    rm -f "$output" "$metrics" "$LOG_BASE/current.pid"
    export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1
    export CONTRACTKV_PREFIX_METRICS_LOG="$metrics" CONTRACTKV_POLICY_HASH="$HASH"
    export CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000 CONTRACTKV_MAX_DEGRADATION=1000000000
    export EXTRA_VLLM_ARGS="--enable-prefix-caching --trust-remote-code"
    bash scripts/run_vllm_server.sh --phase "phase26d-${label}" \
      --model-path "$MODEL" --served-model-name deepseek-coder-v2-lite-instruct --port "$PORT" \
      --gpu-ids "0,1" --tensor-parallel-size 2 --dtype bfloat16 --max-model-len 16384 \
      --max-num-seqs 2 --gpu-memory-utilization .70 --log-path "$log" --pid-path "$LOG_BASE/current.pid"
    "$PY" scripts/phase26d_typed_live.py --sessions "$HELD" --manifest "$MANIFEST" \
      --budgets "$BUDGETS" --base-url "http://127.0.0.1:$PORT/v1" \
      --model deepseek-coder-v2-lite-instruct --model-identity "$MODEL" --mode "$mode" \
      --load-tier "$label" --policy-hash "$HASH" --concurrency 2 --turns 10 \
      --stable-word-limit 1150 --tool-slack-ms 6000 --metrics-events "$metrics" --output "$output"
    bash scripts/stop_vllm_server.sh --pid-path "$LOG_BASE/current.pid" --port "$PORT" >/dev/null 2>&1 || true
  done
done

echo PHASE26D_DEEPSEEK_CODER_HELDOUT_COMPLETE
