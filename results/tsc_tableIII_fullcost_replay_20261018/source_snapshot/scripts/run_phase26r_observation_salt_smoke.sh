#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
SOURCE="${SOURCE_VLLM:-$ROOT/third_party/vllm-contractkv-phase19c}"
MODEL="/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/DeepSeek-Coder-V2-Lite-Instruct"
BASE="$ROOT/results/cross_model/deepseek_phase26r_scope_closure"
SCHEDULER="$SOURCE/vllm/v1/core/sched/scheduler.py"
PORT="${PHASE26R_SMOKE_PORT:-8965}"
OUT="$BASE/observation_salt_smoke"
PID="$ROOT/logs/phase26r_deepseek_coder/salt_smoke.pid"

cd "$ROOT"
mkdir -p "$OUT" "$(dirname "$PID")"
if [[ -n "${PHASE26R_SMOKE_SESSIONS:-}" ]]; then
  cp "$PHASE26R_SMOKE_SESSIONS" "$OUT/sessions.jsonl"
else
  sed -n '1,2p' "$BASE/sealed/heldout_sealed_sessions_v5.jsonl" > "$OUT/sessions.jsonl"
fi
export PYTHONPATH="$SOURCE:$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export VLLM_SERVER_DEV_MODE=1

cleanup() {
  bash scripts/stop_vllm_server.sh --pid-path "$PID" --port "$PORT" >/dev/null 2>&1 || true
  "$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action uninstall >/dev/null 2>&1 || true
  "$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action remove >/dev/null 2>&1 || true
}
trap cleanup EXIT
cleanup
"$PY" scripts/install_vllm_v1_compact_stop_margin.py --source-root "$SOURCE"
"$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action install
"$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action install

MANIFEST="$BASE/frozen_observation_policy_v1.json"
HASH=$("$PY" -c "import json; print(json.load(open('$MANIFEST'))['qualification_hash'])")
MIN_MARGIN=$("$PY" -c "import json; print(json.load(open('$MANIFEST'))['exact_robustness_thresholds']['minimum_candidate_margin_q05'])")
MAX_DEGRADATION=$("$PY" -c "import json; print(json.load(open('$MANIFEST'))['exact_robustness_thresholds']['maximum_degradation_q95'])")
MIN_STOP_MARGIN=$("$PY" -c "import json; print(json.load(open('$MANIFEST'))['exact_robustness_thresholds']['minimum_terminal_stop_margin'])")
export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1
export CONTRACTKV_PREFIX_METRICS_LOG="$OUT/metrics.jsonl" CONTRACTKV_POLICY_HASH="$HASH"
export CONTRACTKV_MIN_CANDIDATE_MARGIN="$MIN_MARGIN" CONTRACTKV_MAX_DEGRADATION="$MAX_DEGRADATION"
export CONTRACTKV_MIN_STOP_MARGIN="$MIN_STOP_MARGIN"
export EXTRA_VLLM_ARGS="--enable-prefix-caching --trust-remote-code"
rm -f "$OUT/metrics.jsonl" "$OUT/requests.jsonl" "$PID"
bash scripts/run_vllm_server.sh --phase phase26r-observation-salt-smoke \
  --model-path "$MODEL" --served-model-name deepseek-coder-v2-lite-instruct --port "$PORT" \
  --gpu-ids 0,1 --tensor-parallel-size 2 --dtype bfloat16 --max-model-len 16384 \
  --max-num-seqs 2 --gpu-memory-utilization .70 \
  --log-path "$ROOT/logs/phase26r_deepseek_coder/salt_smoke_server.log" --pid-path "$PID"
"$PY" scripts/phase26r_observation_live.py --sessions "$OUT/sessions.jsonl" --manifest "$MANIFEST" \
  --budgets "$ROOT/results/cross_model/deepseek_phase26_recoverability/coder/frozen_task_output_budgets_v0.json" \
  --base-url "http://127.0.0.1:$PORT/v1" --model deepseek-coder-v2-lite-instruct \
  --model-identity "$MODEL" --mode contract --load-tier observation-salt-smoke \
  --policy-hash "$HASH" --concurrency 2 --turns "${PHASE26R_SMOKE_TURNS:-3}" --stable-word-limit 1150 \
  --tool-slack-ms 6000 --metrics-events "$OUT/metrics.jsonl" --output "$OUT/requests.jsonl"
"$PY" -c "import json; rows=[json.loads(x) for x in open('$OUT/requests.jsonl') if x.strip()]; assert rows; assert max(int(r.get('dynamic_suffix_reuse_tokens') or 0) for r in rows)==0; print(f'OBSERVATION_SALT_SMOKE_PASS rows={len(rows)} exact={sum(r.get(\"certificate_tier\")==\"EXACT\" for r in rows)} dynamic_suffix_reuse_max=0')"
