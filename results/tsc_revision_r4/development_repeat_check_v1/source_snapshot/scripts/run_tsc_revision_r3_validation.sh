#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
DATA=/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9
PY=/home/user/miniconda3/envs/contractkv-cu128/bin/python
cd "$ROOT"
sha256sum -c results/tsc_revision_r3/validation_v1/source_checksums.sha256
export PYTHONPATH="$ROOT/third_party/vllm-contractkv-tsc-r2-margin:$ROOT" PYTHON_BIN="$PY" VLLM_USE_V1=1
export TMPDIR="$DATA/tmp/contractkv-r1r" HF_HOME="$DATA/datasets/hf_cache"
export CONTRACTKV_POLICY_HASH="$(sha256sum results/tsc_revision_r3/validation_v1/freeze.json | awk '{print $1}')"
export CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000 CONTRACTKV_MAX_DEGRADATION=1000000000
export CONTRACTKV_SHADOW_CHUNK_TOKENS=128 CONTRACTKV_SHADOW_ROUND_TOKENS=128
export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1
unset CONTRACTKV_R2_EXECUTION_TRACE CONTRACTKV_R2_VERIFY_TRACE
export EXTRA_VLLM_ARGS="--enable-prefix-caching --host 127.0.0.1" VLLM_STARTUP_POLLS=360
run_cell() (
  name=$1 study=$2 policy=$3 repeat=$4 gpu=$5 port=$6
  case "$name" in
    qwen) model="$DATA/models/Qwen3-8B"; served=qwen3-8b; identity=Qwen3-8B ;;
    mistral) model="$DATA/models/Mistral-7B-Instruct-v0.3"; served=mistral7b; identity=Mistral-7B-Instruct-v0.3 ;;
    llama) model="$DATA/models/Llama-3.1-8B-Instruct"; served=llama31-8b; identity=Llama-3.1-8B-Instruct ;;
  esac
  cell="${study}_${name}_${policy}_r${repeat}"; base="$ROOT/results/tsc_revision_r3/validation_v1/cells/$cell"
  mkdir -p "$base"; [[ ! -e "$base/raw.jsonl" ]] || exit 41
  sessions=results/tsc_revision_r3/inputs/heldout_sealed_sessions_v1.jsonl; tenants=1
  if [[ "$study" == template-fanout ]]; then sessions=results/tsc_revision_r3/inputs/heldout_fanout_v1.jsonl; tenants=10; fi
  export CONTRACTKV_MIN_RAW_TOKEN_MARGIN=-inf CONTRACTKV_MIN_CANDIDATE_TOKEN_MARGIN=-inf
  if [[ "$policy" == margin-benefit ]]; then
    read -r CONTRACTKV_MIN_RAW_TOKEN_MARGIN CONTRACTKV_MIN_CANDIDATE_TOKEN_MARGIN < <("$PY" -c 'import json;d=json.load(open("configs/tsc_revision_r3_catalog_v1.json"));print(d["raw_token_margin_floor"],d["candidate_token_margin_floor"])')
    export CONTRACTKV_MIN_RAW_TOKEN_MARGIN CONTRACTKV_MIN_CANDIDATE_TOKEN_MARGIN
  fi
  export CONTRACTKV_PREFIX_METRICS_LOG="$base/metrics.jsonl"
  export VLLM_CACHE_ROOT="$ROOT/cache/tsc_revision_r3/validation-$cell/vllm"
  export TRITON_CACHE_DIR="$ROOT/cache/tsc_revision_r3/validation-$cell/triton"
  export TORCHINDUCTOR_CACHE_DIR="$ROOT/cache/tsc_revision_r3/validation-$cell/inductor"
  "$PY" scripts/tsc_revision_r2_runtime_manifest_v2.py --root "$ROOT" --model "$model" --gpu "$gpu" \
    --freeze results/tsc_revision_r3/validation_v1/freeze.json --registry results/tsc_revision_r2/model_registry_v1.json \
    --sessions "$sessions" --cell "$cell" --output "$base/runtime_manifest.json"
  cleanup() { bash scripts/stop_vllm_server.sh --pid-path "$base/server.pid" --port "$port" || true; }
  trap cleanup EXIT
  bash scripts/run_vllm_server.sh --phase "r3-validation-$cell" --model-path "$model" --served-model-name "$served" \
    --port "$port" --gpu-ids "$gpu" --tensor-parallel-size 1 --dtype float16 --max-model-len 16384 \
    --max-num-seqs 2 --gpu-memory-utilization .88 --log-path "$ROOT/logs/tsc_revision_r3/validation_${cell}_server.log" --pid-path "$base/server.pid"
  "$PY" scripts/tsc_revision_r2_prefix_smoke_logged.py --base-url "http://127.0.0.1:$port/v1" --model "$served" \
    --policy-hash "$CONTRACTKV_POLICY_HASH" --repeats 1 --output "$base/pre_measurement_control.jsonl" --evidence "$base/pre_measurement_full_ids.jsonl"
  "$PY" scripts/tsc_revision_r3_live.py --protocol configs/tsc_revision_r1r_validation_protocol_v1.json --catalog configs/tsc_revision_r3_catalog_v1.json \
    --sessions "$sessions" --model "$served" --model-identity "$identity" --study "$study" --policy "$policy" \
    --base-url "http://127.0.0.1:$port/v1" --cell-id "$cell" --policy-hash "$CONTRACTKV_POLICY_HASH" --repeat "$repeat" \
    --tenants-per-template "$tenants" --output "$base/raw.jsonl" --summary "$base/summary.json" --metrics-events "$base/metrics.jsonl"
  echo "R3_VALIDATION_CELL_COMPLETE $cell"
)
worker() {
  lane=$1;index=0
  for study in single-session template-fanout; do
    for repeat in 1 2 3; do
      case "$repeat" in
        1) policies=(raw-order margin-benefit) ;;
        2) policies=(margin-benefit raw-order) ;;
        3) policies=(raw-order margin-benefit) ;;
      esac
      for name in qwen mistral llama; do
        if (( index % 2 == lane )); then
          for policy in "${policies[@]}"; do run_cell "$name" "$study" "$policy" "$repeat" "$lane" "$((9912+lane))"; done
        fi
        index=$((index+1))
      done
    done
  done
}
worker 0 & p0=$!
worker 1 & p1=$!
failed=0; wait "$p0" || failed=1; wait "$p1" || failed=1
[[ "$failed" == 0 ]] || exit 31
echo R3_INDEPENDENT_VALIDATION_V1_COMPLETE
