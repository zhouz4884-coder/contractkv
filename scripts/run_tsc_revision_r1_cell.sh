#!/usr/bin/env bash
# Fresh serving cell; all files and compilation caches stay on the data disk.
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
DATA="${CONTRACTKV_DISK_ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
experiment=$1 model=$2 policy=$3 repeat=$4 gpu=$5 port=$6 sessions=$7 budget=${8:-0}
cell="${experiment}_${model}_r${repeat}_${policy}_b${budget}"
SOURCE="$ROOT/third_party/vllm-contractkv-tsc-r1"
dir="$ROOT/results/tsc_revision_r1/cells/$cell"
log="$ROOT/logs/tsc_revision_r1/${cell}_server.log"
if [[ -e "$dir/raw.jsonl" ]]; then
  echo "Existing attempt retained; use an explicit new attempt directory." >&2
  exit 41
fi
mkdir -p "$dir" "$ROOT/logs/tsc_revision_r1" "$DATA/tmp/contractkv-r1"
cd "$ROOT"
case "$model" in
  qwen) model_path="$DATA/models/Qwen3-8B"; identity=Qwen3-8B; served=qwen3-8b ;;
  mistral) model_path="$DATA/models/Mistral-7B-Instruct-v0.3"; identity=Mistral-7B-Instruct-v0.3; served=mistral7b ;;
  llama) model_path="$DATA/models/Llama-3.1-8B-Instruct"; identity=Llama-3.1-8B-Instruct; served=llama31-8b ;;
  *) echo "Unknown model $model" >&2; exit 2 ;;
esac
export PYTHONPATH="$SOURCE:$ROOT${PYTHONPATH:+:$PYTHONPATH}" PYTHON_BIN="$PY" VLLM_USE_V1=1
export TMPDIR="$DATA/tmp/contractkv-r1"
export RUNTIME_TMP_REAL="$TMPDIR"
export XDG_CACHE_HOME="$ROOT/cache/tsc_revision_r1/$cell/xdg"
export HF_HOME="$DATA/datasets/hf_cache"
export HF_DATASETS_CACHE="$HF_HOME/datasets"
export VLLM_CACHE_ROOT="$ROOT/cache/tsc_revision_r1/$cell/vllm"
export TRITON_CACHE_DIR="$ROOT/cache/tsc_revision_r1/$cell/triton"
export TORCHINDUCTOR_CACHE_DIR="$ROOT/cache/tsc_revision_r1/$cell/torchinductor"
export CONTRACTKV_POLICY_HASH="$(sha256sum configs/tsc_major_revision_r1_protocol.json | awk '{print $1}')"
export CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000 CONTRACTKV_MAX_DEGRADATION=1000000000
export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1 CONTRACTKV_PREFIX_CONCURRENT_SNAPSHOTS=1
export CONTRACTKV_PREFIX_METRICS_LOG="$dir/metrics.jsonl"
export CONTRACTKV_SHADOW_QUANTUM=32 CONTRACTKV_SHADOW_ROUND_TOKENS=32
export VLLM_STARTUP_POLLS=360 EXTRA_VLLM_ARGS="--enable-prefix-caching --host 127.0.0.1"
"$PY" scripts/tsc_revision_cell_manifest.py --root "$ROOT" --source "$SOURCE" --model "$model_path" \
  --sessions "$sessions" --output "$dir/cell_manifest.json" --cell "$cell" --gpu "$gpu" --budget "$budget"
cleanup() { bash scripts/stop_vllm_server.sh --pid-path "$dir/server.pid" --port "$port" || true; }
trap cleanup EXIT
bash scripts/run_vllm_server.sh --phase "$cell" --model-path "$model_path" --served-model-name "$served" \
  --port "$port" --gpu-ids "$gpu" --tensor-parallel-size 1 --dtype float16 --max-model-len 16384 \
  --max-num-seqs 2 --gpu-memory-utilization .88 --log-path "$log" --pid-path "$dir/server.pid"
"$PY" scripts/tsc_revision_live.py --protocol configs/tsc_major_revision_r1_protocol.json \
  --sessions "$sessions" --experiment "$experiment" --policy "$policy" --repeat "$repeat" \
  --model "$served" --model-identity "$identity" --base-url "http://127.0.0.1:$port/v1" \
  --cell-id "$cell" --policy-hash "$CONTRACTKV_POLICY_HASH" --output-budget "$budget" \
  --output "$dir/raw.jsonl" --summary "$dir/summary.json" --metrics-events "$dir/metrics.jsonl"
