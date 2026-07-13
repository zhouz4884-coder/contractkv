#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
MODEL="${MODEL_PATH:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-8B}"
SOURCE="${SOURCE_VLLM:-$ROOT/third_party/vllm-contractkv}"
OUT="$ROOT/results/hard_systems/physical_dedup_submission_cells"
LOG="$ROOT/logs/physical_dedup_submission"
SCHEDULER="$SOURCE/vllm/v1/core/sched/scheduler.py"
cd "$ROOT"; mkdir -p "$OUT" "$LOG"
export PYTHONPATH="$SOURCE:$ROOT${PYTHONPATH:+:$PYTHONPATH}"
"$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action install
cleanup_all(){
  "$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action uninstall >/dev/null 2>&1 || true
}
trap cleanup_all EXIT

for repeat in 1 2 3; do
  for sessions in 10 20; do
    if (( repeat % 2 == 1 )); then order="raw-order contractkv-caposc"; else order="contractkv-caposc raw-order"; fi
    for policy in $order; do
      cell="physical-dedup-r${repeat}-n${sessions}-${policy}"
      metrics="$OUT/${cell}_metrics.jsonl"; raw="$OUT/${cell}_raw.csv"; summary="$OUT/${cell}_summary.csv"
      pid="$LOG/${cell}.pid"; server_log="$LOG/${cell}_server.log"; port=$((8300 + repeat * 10 + sessions / 10))
      [[ -s "$raw" && -s "$summary" ]] && { echo "SKIP $cell"; continue; }
      rm -f "$metrics" "$raw" "$summary" "$pid"
      export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_METRICS_LOG="$metrics"
      export CONTRACTKV_PREFIX_CONCURRENT_SNAPSHOTS=1 EXTRA_VLLM_ARGS="--enable-prefix-caching"
      bash scripts/run_vllm_server.sh --phase "$cell" --model-path "$MODEL" --served-model-name qwen3-8b \
        --port "$port" --gpu-ids 0 --tensor-parallel-size 1 --dtype float16 --max-model-len 8192 \
        --max-num-seqs "$sessions" --gpu-memory-utilization .88 --log-path "$server_log" --pid-path "$pid"
      set +e
      "$PY" scripts/phase14m_physical_dedup.py --experiment warm --policy "$policy" \
        --shared-target-tokens 4096 --sessions "$sessions" --tokenizer "$MODEL" \
        --metrics-events "$metrics" --base-url "http://127.0.0.1:$port/v1" --model qwen3-8b \
        --max-tokens 16 --cell-id "$cell" --raw-output "$raw" --summary-output "$summary"
      rc=$?
      set -e
      bash scripts/stop_vllm_server.sh --pid-path "$pid" --port "$port" || true
      [[ $rc -eq 0 ]] || echo "CAPACITY_FAILURE cell=$cell rc=$rc" | tee "$OUT/${cell}_capacity_failure.txt"
    done
  done
done
"$PY" scripts/summarize_physical_dedup_memory.py --cell-dir "$OUT" --model-config "$MODEL/config.json" \
  --model Qwen3-8B --output "$ROOT/results/hard_systems/physical_dedup_memory_v0.csv" \
  --json-output "$ROOT/results/hard_systems/physical_dedup_memory_v0.json"
echo PHYSICAL_DEDUP_SUBMISSION_COMPLETE
