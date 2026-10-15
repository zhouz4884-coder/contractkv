#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
DATA=/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9
PY=/home/user/miniconda3/envs/contractkv-cu128/bin/python
cd "$ROOT"
sha256sum -c results/tsc_revision_r2/long_format_v2/source_checksums.sha256
export PYTHONPATH="$ROOT/third_party/vllm-contractkv-tsc-r2-margin:$ROOT" PYTHON_BIN="$PY" VLLM_USE_V1=1
export TMPDIR="$DATA/tmp/contractkv-r1r" HF_HOME="$DATA/datasets/hf_cache"
export CONTRACTKV_POLICY_HASH="$(sha256sum results/tsc_revision_r2/long_format_v2/freeze.json | awk '{print $1}')"
export CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000 CONTRACTKV_MAX_DEGRADATION=1000000000
read -r CONTRACTKV_MIN_RAW_TOKEN_MARGIN CONTRACTKV_MIN_CANDIDATE_TOKEN_MARGIN < <("$PY" -c 'import json;d=json.load(open("configs/tsc_revision_r2_selected_catalog_v2.json"));print(d["raw_token_margin_floor"],d["candidate_token_margin_floor"])')
export CONTRACTKV_MIN_RAW_TOKEN_MARGIN CONTRACTKV_MIN_CANDIDATE_TOKEN_MARGIN
export CONTRACTKV_SHADOW_CHUNK_TOKENS=128 CONTRACTKV_SHADOW_ROUND_TOKENS=128
export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1
unset CONTRACTKV_R2_EXECUTION_TRACE CONTRACTKV_R2_VERIFY_TRACE
export EXTRA_VLLM_ARGS="--enable-prefix-caching --host 127.0.0.1" VLLM_STARTUP_POLLS=360
run_cell() (
  name=$1 repeat=$2 gpu=$3 port=$4
  case "$name" in
    qwen) model="$DATA/models/Qwen3-8B"; served=qwen3-8b ;;
    mistral) model="$DATA/models/Mistral-7B-Instruct-v0.3"; served=mistral7b ;;
    llama) model="$DATA/models/Llama-3.1-8B-Instruct"; served=llama31-8b ;;
  esac
  cell="long-format-v2_${name}_r${repeat}"; base="$ROOT/results/tsc_revision_r2/long_format_v2/cells/$cell"
  mkdir -p "$base"; [[ ! -e "$base/raw.jsonl" ]] || exit 41
  export CONTRACTKV_PREFIX_METRICS_LOG="$base/metrics.jsonl"
  export VLLM_CACHE_ROOT="$ROOT/cache/tsc_revision_r2/$cell/vllm"
  export TRITON_CACHE_DIR="$ROOT/cache/tsc_revision_r2/$cell/triton"
  export TORCHINDUCTOR_CACHE_DIR="$ROOT/cache/tsc_revision_r2/$cell/inductor"
  "$PY" scripts/tsc_revision_r2_runtime_manifest_v2.py --root "$ROOT" --model "$model" --gpu "$gpu" \
    --freeze results/tsc_revision_r2/long_format_v2/freeze.json --registry results/tsc_revision_r2/model_registry_v1.json \
    --sessions configs/tsc_revision_r2_long_format_v2.json --cell "$cell" --output "$base/runtime_manifest.json"
  cleanup() { bash scripts/stop_vllm_server.sh --pid-path "$base/server.pid" --port "$port" || true; }
  trap cleanup EXIT
  bash scripts/run_vllm_server.sh --phase "$cell" --model-path "$model" --served-model-name "$served" \
    --port "$port" --gpu-ids "$gpu" --tensor-parallel-size 1 --dtype float16 --max-model-len 16384 \
    --max-num-seqs 2 --gpu-memory-utilization .88 --log-path "$ROOT/logs/tsc_revision_r2/${cell}_server.log" --pid-path "$base/server.pid"
  "$PY" scripts/tsc_revision_r2_prefix_smoke_logged.py --base-url "http://127.0.0.1:$port/v1" --model "$served" \
    --policy-hash "$CONTRACTKV_POLICY_HASH" --repeats 1 --output "$base/pre_measurement_control.jsonl" --evidence "$base/pre_measurement_full_ids.jsonl"
  "$PY" scripts/tsc_revision_r2_long_format.py --protocol configs/tsc_revision_r2_long_format_v2.json \
    --catalog configs/tsc_revision_r2_selected_catalog_v2.json --model "$served" --repeat "$repeat" --base-url "http://127.0.0.1:$port/v1" \
    --policy-hash "$CONTRACTKV_POLICY_HASH" --output "$base/raw.jsonl" --metrics "$base/metrics.jsonl"
  echo "R2_LONG_FORMAT_CELL_COMPLETE $cell"
)
worker() {
  lane=$1
  if [[ "$lane" == 0 ]]; then models=(qwen); else models=(mistral llama); fi
  for name in "${models[@]}"; do for repeat in 1 2 3; do run_cell "$name" "$repeat" "$lane" "$((9904+lane))"; done; done
}

run_cell "$1" "$2" "$3" "$4"
