#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
MODEL_PATH="${MODEL_PATH:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-8B}"
SOURCE_VLLM="${SOURCE_VLLM:-$ROOT/third_party/vllm-contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
POLICY_HASH="55e10dc4f54daf428b382a35fe8a8feeded5b4b3f34752f36f45c8f825df1ee4"
OUT="$ROOT/results/end_to_end/phase19b_cells"
LOG="$ROOT/logs/phase19b"
SCHEDULER="$SOURCE_VLLM/vllm/v1/core/sched/scheduler.py"
mkdir -p "$OUT" "$LOG" "$ROOT/results/end_to_end"
cd "$ROOT"
export PYTHONPATH="$SOURCE_VLLM:$ROOT${PYTHONPATH:+:$PYTHONPATH}"

if nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | grep -q '[0-9]'; then
  echo "GPU compute process already exists; refusing to mix a stale process into Phase 19B" >&2
  nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader >&2
  exit 20
fi

"$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action install
cleanup_probe(){ "$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action uninstall || true; }
trap cleanup_probe EXIT

"$PY" scripts/phase19b_build_task_sessions.py --full-pool results/workload/phase14d_full_pool_v2.jsonl \
  --phase19a-quality results/quality/phase19a_frozen_quality_v0.csv --per-family 10 \
  --output results/end_to_end/phase19b_untouched_sessions_v0.jsonl

run_cell(){
  local cell=$1 tier=$2 conc=$3 policy=$4 port=$5 gpu=$6
  (
    set -euo pipefail
    metrics="$OUT/${cell}_metrics.jsonl"; server_log="$LOG/${cell}_server.log"; pid="$LOG/${cell}.pid"; output="$OUT/${cell}.jsonl"
    rm -f "$metrics" "$pid" "$output"
    export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1 CONTRACTKV_PREFIX_METRICS_LOG="$metrics"
    export CONTRACTKV_POLICY_HASH="$POLICY_HASH" CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000 CONTRACTKV_MAX_DEGRADATION=1000000000
    export EXTRA_VLLM_ARGS="--enable-prefix-caching"
    cleanup_cell(){ bash scripts/stop_vllm_server.sh --pid-path "$pid" --port "$port" || true; }
    trap cleanup_cell EXIT
    bash scripts/run_vllm_server.sh --phase "phase19b-$cell" --model-path "$MODEL_PATH" \
      --served-model-name qwen3-8b --port "$port" --gpu-ids "$gpu" --tensor-parallel-size 1 \
      --dtype float16 --max-model-len 8192 --max-num-seqs 2 --gpu-memory-utilization 0.88 \
      --log-path "$server_log" --pid-path "$pid"
    "$PY" scripts/phase19b_end_to_end_live.py --sessions results/end_to_end/phase19b_untouched_sessions_v0.jsonl \
      --base-url "http://127.0.0.1:$port/v1" --model qwen3-8b --policy "$policy" --policy-hash "$POLICY_HASH" \
      --load-tier "$tier" --concurrency "$conc" --turns 10 --max-tokens 96 --metrics-events "$metrics" --output "$output"
  )
}

policies=(raw-order contractkv-full static-dependency-layout physical-cache-aware)
tiers=(low transition saturation)
concurrency=(1 2 4)
inputs=(); pids=(); cell_index=0
for ti in 0 1 2; do
  tier="${tiers[$ti]}"; conc="${concurrency[$ti]}"
  for policy in "${policies[@]}"; do
    cell="${tier}_${policy}"; port=$((8030 + cell_index)); gpu=$((cell_index % 2))
    inputs+=("$OUT/${cell}.jsonl")
    run_cell "$cell" "$tier" "$conc" "$policy" "$port" "$gpu" &
    pids+=("$!"); cell_index=$((cell_index + 1))
    if [[ ${#pids[@]} -eq 2 ]]; then
      failed=0
      for child in "${pids[@]}"; do wait "$child" || failed=1; done
      pids=()
      [[ $failed -eq 0 ]] || exit 21
    fi
  done
done
"$PY" scripts/phase19b_summarize_net_benefit.py --inputs "${inputs[@]}" \
  --raw-output results/end_to_end/phase19b_task_replay_raw_v0.jsonl \
  --summary-output results/end_to_end/phase19b_task_replay_summary_v0.csv \
  --gate-output results/end_to_end/phase19b_task_replay_gate_v0.json
echo PHASE19B_COMPLETE
