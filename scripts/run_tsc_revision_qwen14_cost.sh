#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
DATA=/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9
PY=/home/user/miniconda3/envs/contractkv-cu128/bin/python
cd "$ROOT"
SOURCE="$ROOT/third_party/vllm-contractkv-tsc-r1"
export PYTHONPATH="$SOURCE:$ROOT${PYTHONPATH:+:$PYTHONPATH}" PYTHON_BIN="$PY" VLLM_USE_V1=1
export TMPDIR="$DATA/tmp/contractkv-r1" HF_HOME="$DATA/datasets/hf_cache"
export CONTRACTKV_POLICY_HASH="$(sha256sum configs/tsc_revision_qwen14_cost_protocol_v1.json | awk '{print $1}')"
export CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000 CONTRACTKV_MAX_DEGRADATION=1000000000
export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1 CONTRACTKV_PREFIX_CONCURRENT_SNAPSHOTS=1
export EXTRA_VLLM_ARGS="--enable-prefix-caching --host 127.0.0.1" VLLM_STARTUP_POLLS=360
run_cell() (
  repeat=$1 policy=$2; cell="qwen14-full-cost_qwen14_r${repeat}_${policy}_b96"
  dir="$ROOT/results/tsc_revision_r1/cells/$cell"; mkdir -p "$dir"
  if [[ -s "$dir/summary.json" ]]; then echo "SKIP_COMPLETE $cell"; return; fi
  [[ ! -e "$dir/raw.jsonl" ]] || { echo "Existing cost attempt requires inspection"; exit 41; }
  export CONTRACTKV_PREFIX_METRICS_LOG="$dir/metrics.jsonl"
  export VLLM_CACHE_ROOT="$ROOT/cache/tsc_revision_r1/$cell/vllm"
  export TRITON_CACHE_DIR="$ROOT/cache/tsc_revision_r1/$cell/triton"
  export TORCHINDUCTOR_CACHE_DIR="$ROOT/cache/tsc_revision_r1/$cell/torchinductor"
  "$PY" scripts/tsc_revision_cell_manifest.py --root "$ROOT" --source "$SOURCE" --model "$DATA/models/Qwen3-14B" \
    --sessions results/tsc_revision_r1/inputs/qwen14_cost_sessions_v1.jsonl --output "$dir/cell_manifest.json" \
    --cell "$cell" --gpu 0,1 --budget 96
  cleanup() { bash scripts/stop_vllm_server.sh --pid-path "$dir/server.pid" --port 9870 || true; }
  trap cleanup EXIT
  bash scripts/run_vllm_server.sh --phase "$cell" --model-path "$DATA/models/Qwen3-14B" --served-model-name qwen3-14b \
    --port 9870 --gpu-ids 0,1 --tensor-parallel-size 2 --dtype float16 --max-model-len 8192 --max-num-seqs 2 \
    --gpu-memory-utilization .88 --log-path "$ROOT/logs/tsc_revision_r1/${cell}_server.log" --pid-path "$dir/server.pid"
  "$PY" scripts/tsc_revision_qwen14_cost_live.py --protocol configs/tsc_major_revision_r1_protocol.json \
    --sessions results/tsc_revision_r1/inputs/qwen14_cost_sessions_v1.jsonl --experiment free-generation \
    --policy "$policy" --repeat "$repeat" --model qwen3-14b --model-identity Qwen3-14B \
    --base-url http://127.0.0.1:9870/v1 --cell-id "$cell" --policy-hash "$CONTRACTKV_POLICY_HASH" \
    --output-budget 96 --output "$dir/raw.jsonl" --summary "$dir/summary.json" --metrics-events "$dir/metrics.jsonl"
)
for repeat in 1 2 3; do
  if [[ $repeat == 2 ]]; then policies=(contractkv raw-order); else policies=(raw-order contractkv); fi
  for policy in "${policies[@]}"; do run_cell "$repeat" "$policy"; done
done
echo QWEN14_FULL_COST_COMPLETE
