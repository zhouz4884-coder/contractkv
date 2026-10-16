#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
DATA=/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9
PY=/home/user/miniconda3/envs/contractkv-cu128/bin/python
cd "$ROOT"
sha256sum -c results/tsc_revision_r4/diagnosis_v1/source_checksums.sha256
export PYTHONPATH="$ROOT/third_party/vllm-contractkv-tsc-r2-margin:$ROOT" PYTHON_BIN="$PY" VLLM_USE_V1=1
export TMPDIR="$DATA/tmp/contractkv-r1r" HF_HOME="$DATA/datasets/hf_cache"
export CONTRACTKV_POLICY_HASH="$(sha256sum results/tsc_revision_r4/diagnosis_v1/freeze.json | awk '{print $1}')"
export CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000 CONTRACTKV_MAX_DEGRADATION=1000000000
export CONTRACTKV_MIN_RAW_TOKEN_MARGIN=.0625 CONTRACTKV_MIN_CANDIDATE_TOKEN_MARGIN=.125
export CONTRACTKV_SHADOW_CHUNK_TOKENS=128 CONTRACTKV_SHADOW_ROUND_TOKENS=128
export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1
export EXTRA_VLLM_ARGS="--enable-prefix-caching --host 127.0.0.1" VLLM_STARTUP_POLLS=360
run_lane() (
  gpu=$1;port=$((9914+gpu));cell="qwen_gpu${gpu}";base="$ROOT/results/tsc_revision_r4/diagnosis_v1/cells/$cell"
  mkdir -p "$base";[[ ! -e "$base/raw.jsonl" ]] || exit 41
  export CONTRACTKV_PREFIX_METRICS_LOG="$base/metrics.jsonl"
  export CONTRACTKV_R2_EXECUTION_TRACE="$base/execution_trace.jsonl" CONTRACTKV_R2_VERIFY_TRACE="$base/verify_trace.jsonl"
  export VLLM_CACHE_ROOT="$ROOT/cache/tsc_revision_r4/diagnosis-$cell/vllm"
  export TRITON_CACHE_DIR="$ROOT/cache/tsc_revision_r4/diagnosis-$cell/triton"
  export TORCHINDUCTOR_CACHE_DIR="$ROOT/cache/tsc_revision_r4/diagnosis-$cell/inductor"
  "$PY" scripts/tsc_revision_r2_runtime_manifest_v2.py --root "$ROOT" --model "$DATA/models/Qwen3-8B" --gpu "$gpu" \
    --freeze results/tsc_revision_r4/diagnosis_v1/freeze.json --registry results/tsc_revision_r4/model_registry_v1.json \
    --sessions results/tsc_revision_r4/known_case_v1/sessions.jsonl --cell "$cell" --output "$base/runtime_manifest.json"
  cleanup() { bash scripts/stop_vllm_server.sh --pid-path "$base/server.pid" --port "$port" || true; }
  trap cleanup EXIT
  bash scripts/run_vllm_server.sh --phase "r4-known-$cell" --model-path "$DATA/models/Qwen3-8B" --served-model-name qwen3-8b \
    --port "$port" --gpu-ids "$gpu" --tensor-parallel-size 1 --dtype float16 --max-model-len 16384 \
    --max-num-seqs 2 --gpu-memory-utilization .88 --log-path "$ROOT/logs/tsc_revision_r4/diagnosis_${cell}_server.log" --pid-path "$base/server.pid"
  "$PY" scripts/tsc_revision_r4_known_diagnosis.py --protocol configs/tsc_revision_r1r_validation_protocol_v1.json \
    --config configs/tsc_revision_r4_known_diagnosis_v1.json --sessions results/tsc_revision_r4/known_case_v1/sessions.jsonl \
    --prompt-evidence results/tsc_revision_r4/known_case_v1/actual_prompt_ids_v1.json --base-url "http://127.0.0.1:$port/v1" \
    --policy-hash "$CONTRACTKV_POLICY_HASH" --cell-id "$cell" --output "$base/raw.jsonl" --metrics "$base/metrics.jsonl" --summary "$base/summary.json"
  echo "R4_KNOWN_DIAGNOSIS_CELL_COMPLETE $cell"
)
run_lane 0 & p0=$!
run_lane 1 & p1=$!
failed=0;wait "$p0" || failed=1;wait "$p1" || failed=1
[[ "$failed" == 0 ]] || exit 31
echo R4_KNOWN_DIAGNOSIS_V1_COMPLETE
