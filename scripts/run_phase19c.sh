#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
MODEL_PATH="${MODEL_PATH:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Llama-3.1-8B-Instruct}"
SOURCE_VLLM="${SOURCE_VLLM:-$ROOT/third_party/vllm-contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
GPU_IDS="${GPU_IDS:-1}"
OUT="$ROOT/results/cross_model/phase19c_cells"; LOG="$ROOT/logs/phase19c"; SCHEDULER="$SOURCE_VLLM/vllm/v1/core/sched/scheduler.py"
mkdir -p "$OUT" "$LOG" "$ROOT/results/cross_model";cd "$ROOT";export PYTHONPATH="$SOURCE_VLLM:$ROOT${PYTHONPATH:+:$PYTHONPATH}"
if nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | grep -q '[0-9]'; then
  echo "GPU compute process already exists; refusing to mix a stale process into Phase 19C" >&2
  nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader >&2
  exit 20
fi
"$PY" scripts/phase19c_prepare_cross_model.py --full-pool results/workload/phase14d_full_pool_v2.jsonl --phase19b-sessions results/end_to_end/phase19b_untouched_sessions_v0.jsonl \
 --model-id llama-3.1-8b-instruct --model-path "$MODEL_PATH" --calibration-output results/cross_model/phase19c_calibration_sessions_v0.jsonl \
 --heldout-output results/cross_model/phase19c_heldout_sessions_v0.jsonl --policy-output results/cross_model/phase19c_frozen_policy_v0.json
POLICY_HASH=$("$PY" -c 'import json;print(json.load(open("results/cross_model/phase19c_frozen_policy_v0.json"))["policy_hash"])')
"$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action install
cleanup_probe(){ "$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action uninstall || true; }
trap cleanup_probe EXIT
run_cell(){
  local name=$1 sessions=$2 policy=$3 concurrency=$4 port=$5 gpu=$6
  (
    set -euo pipefail
    local metrics="$OUT/${name}_metrics.jsonl" output="$OUT/${name}.jsonl" server_log="$LOG/${name}_server.log" pid="$LOG/${name}.pid"
    rm -f "$metrics" "$output" "$pid"
    export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1 CONTRACTKV_PREFIX_METRICS_LOG="$metrics"
    export CONTRACTKV_POLICY_HASH="$POLICY_HASH" CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000 CONTRACTKV_MAX_DEGRADATION=1000000000 EXTRA_VLLM_ARGS="--enable-prefix-caching"
    cleanup_cell(){ bash scripts/stop_vllm_server.sh --pid-path "$pid" --port "$port" || true; }
    trap cleanup_cell EXIT
    bash scripts/run_vllm_server.sh --phase "phase19c-$name" --model-path "$MODEL_PATH" --served-model-name llama31-8b --port "$port" --gpu-ids "$gpu" \
     --tensor-parallel-size 1 --dtype float16 --max-model-len 8192 --max-num-seqs 2 --gpu-memory-utilization .88 --log-path "$server_log" --pid-path "$pid"
    "$PY" scripts/phase19b_end_to_end_live.py --sessions "$sessions" --base-url "http://127.0.0.1:$port/v1" --model llama31-8b --policy "$policy" \
     --policy-hash "$POLICY_HASH" --load-tier transition --concurrency "$concurrency" --turns 10 --max-tokens 96 --metrics-events "$metrics" --output "$output"
  )
}
calibration_inputs=(
  "$OUT/calibration_raw-order.jsonl"
  "$OUT/calibration_physical-cache-aware.jsonl"
  "$OUT/calibration_contractkv-full.jsonl"
)
run_cell calibration_raw-order results/cross_model/phase19c_calibration_sessions_v0.jsonl raw-order 1 8040 0 & p0=$!
run_cell calibration_physical-cache-aware results/cross_model/phase19c_calibration_sessions_v0.jsonl physical-cache-aware 1 8041 1 & p1=$!
failed=0; wait "$p0" || failed=1; wait "$p1" || failed=1; [[ $failed -eq 0 ]] || exit 21
run_cell calibration_contractkv-full results/cross_model/phase19c_calibration_sessions_v0.jsonl contractkv-full 1 8042 "$GPU_IDS"
"$PY" scripts/phase19c_freeze_quality_labels.py --inputs "${calibration_inputs[@]}" --policy-hash "$POLICY_HASH" \
 --output-csv results/cross_model/phase19c_calibration_quality_labels_v0.csv \
 --output-json results/cross_model/phase19c_calibration_quality_summary_v0.json
POLICY_HASH=$("$PY" scripts/phase19c_finalize_model_policy.py --draft results/cross_model/phase19c_frozen_policy_v0.json \
 --calibration-labels results/cross_model/phase19c_calibration_quality_labels_v0.csv \
 --calibration-summary results/cross_model/phase19c_calibration_quality_summary_v0.json \
 --output results/cross_model/phase19c_frozen_policy_v0.json)

inputs=(); pids=(); index=0
for policy in raw-order contractkv-full static-dependency-layout physical-cache-aware;do
  name="heldout_${policy}"; port=$((8043 + index)); gpu=$((index % 2))
  inputs+=("$OUT/${name}.jsonl")
  run_cell "$name" results/cross_model/phase19c_heldout_sessions_v0.jsonl "$policy" 2 "$port" "$gpu" &
  pids+=("$!"); index=$((index + 1))
  if [[ ${#pids[@]} -eq 2 ]]; then
    failed=0
    for child in "${pids[@]}"; do wait "$child" || failed=1; done
    pids=()
    [[ $failed -eq 0 ]] || exit 21
  fi
done
set +e
"$PY" scripts/phase19b_summarize_net_benefit.py --inputs "${inputs[@]}" --expected-full-cells 1 \
 --min-certificate-coverage 0 --min-safe-coverage .50 --min-certified-prefix-hit-fraction .95 \
 --min-net-ttft-reduction 0 --min-new-prefill-reduction .30 --min-retained-prefix-gain .50 \
 --raw-output results/cross_model/phase19c_task_replay_raw_v0.jsonl --summary-output results/cross_model/phase19c_summary_v0.csv \
 --gate-output results/cross_model/phase19c_gate_v0.json
gate_rc=$?
set -e
"$PY" scripts/phase19c_freeze_quality_labels.py --inputs "${inputs[@]}" --policy-hash "$POLICY_HASH" \
 --output-csv results/cross_model/phase19c_heldout_quality_labels_v0.csv \
 --output-json results/cross_model/phase19c_heldout_quality_summary_v0.json
[[ $gate_rc -eq 0 ]] || exit "$gate_rc"
echo PHASE19C_COMPLETE
