#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
SOURCE="${VLLM_SOURCE:-$ROOT/third_party/vllm-contractkv-phase19c}"
SCHEDULER="$SOURCE/vllm/v1/core/sched/scheduler.py"; MODEL=/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Qwen3-8B
OUT="$ROOT/results/tsc_service/lifecycle"; LOG="$ROOT/logs/tsc_service/lifecycle"; mkdir -p "$OUT" "$LOG" "$ROOT/cache/tsc-lifecycle"
cd "$ROOT"; export PYTHONPATH="$SOURCE:$ROOT${PYTHONPATH:+:$PYTHONPATH}" VLLM_STARTUP_POLLS="${VLLM_STARTUP_POLLS:-360}"
"$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action install
pid="$OUT/server.pid"
cleanup(){ bash scripts/stop_vllm_server.sh --pid-path "$pid" --port 8801 || true; "$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action uninstall >/dev/null 2>&1 || true; }
trap cleanup EXIT
export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1 CONTRACTKV_PREFIX_METRICS_LOG="$OUT/metrics.jsonl" EXTRA_VLLM_ARGS="--enable-prefix-caching"
rm -f "$OUT/metrics.jsonl" "$OUT/lifecycle_events_v0.csv" "$OUT/lifecycle_summary_v0.json"
VLLM_CACHE_ROOT="$ROOT/cache/tsc-lifecycle/vllm" TRITON_CACHE_DIR="$ROOT/cache/tsc-lifecycle/triton" \
bash scripts/run_vllm_server.sh --phase tsc-service-lifecycle --model-path "$MODEL" --served-model-name qwen3-8b \
  --port 8801 --gpu-ids 0 --tensor-parallel-size 1 --dtype float16 --max-model-len 8192 --max-num-seqs 4 \
  --gpu-memory-utilization .88 --log-path "$LOG/server.log" --pid-path "$pid"
"$PY" scripts/tsc_service_lifecycle_live.py --tokenizer "$MODEL" --base-url http://127.0.0.1:8801/v1 --model qwen3-8b \
  --metrics-events "$OUT/metrics.jsonl" --phase18-faults "$ROOT/results/hard_systems/phase18_c3_lifecycle_faults_v0.json" \
  --phase18-wire "$ROOT/results/hard_systems/phase18_c3_wire_lifecycle_v0.csv" \
  --raw-output "$OUT/lifecycle_events_v0.csv" --summary-output "$OUT/lifecycle_summary_v0.json"
