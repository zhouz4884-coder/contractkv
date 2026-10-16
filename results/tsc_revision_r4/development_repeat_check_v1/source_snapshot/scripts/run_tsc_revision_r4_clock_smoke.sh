#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
DATA=/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9
PY=/home/user/miniconda3/envs/contractkv-cu128/bin/python
cd "$ROOT"
sha256sum -c results/tsc_revision_r4/clock_smoke_v1/source_checksums.sha256
export PYTHONPATH="$ROOT/third_party/vllm-contractkv-tsc-r2-margin:$ROOT" PYTHON_BIN="$PY" VLLM_USE_V1=1
export TMPDIR="$DATA/tmp/contractkv-r1r" HF_HOME="$DATA/datasets/hf_cache"
export CONTRACTKV_POLICY_HASH="$(sha256sum results/tsc_revision_r4/clock_smoke_v1/freeze.json | awk '{print $1}')"
export CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000 CONTRACTKV_MAX_DEGRADATION=1000000000
export CONTRACTKV_SHADOW_CHUNK_TOKENS=128 CONTRACTKV_SHADOW_ROUND_TOKENS=128
export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1
unset CONTRACTKV_R2_EXECUTION_TRACE CONTRACTKV_R2_VERIFY_TRACE
export EXTRA_VLLM_ARGS="--enable-prefix-caching --host 127.0.0.1" VLLM_STARTUP_POLLS=360
for policy in raw-order risk-tail;do (
  cell="single-session_qwen_${policy}_r1";base="$ROOT/results/tsc_revision_r4/clock_smoke_v1/cells/$cell";port=9918
  mkdir -p "$base";[[ ! -e "$base/raw.jsonl" ]] || exit 41
  export CONTRACTKV_MIN_RAW_TOKEN_MARGIN=-inf CONTRACTKV_MIN_CANDIDATE_TOKEN_MARGIN=-inf
  if [[ "$policy" != raw-order ]];then export CONTRACTKV_MIN_RAW_TOKEN_MARGIN=.0625 CONTRACTKV_MIN_CANDIDATE_TOKEN_MARGIN=.125;fi
  export CONTRACTKV_PREFIX_METRICS_LOG="$base/metrics.jsonl"
  export VLLM_CACHE_ROOT="$ROOT/cache/tsc_revision_r4/clock-$cell/vllm" TRITON_CACHE_DIR="$ROOT/cache/tsc_revision_r4/clock-$cell/triton" TORCHINDUCTOR_CACHE_DIR="$ROOT/cache/tsc_revision_r4/clock-$cell/inductor"
  "$PY" scripts/tsc_revision_r2_runtime_manifest_v2.py --root "$ROOT" --model "$DATA/models/Qwen3-8B" --gpu 0 --freeze results/tsc_revision_r4/clock_smoke_v1/freeze.json --registry results/tsc_revision_r4/model_registry_v1.json --sessions results/tsc_revision_r4/clock_smoke_v1/sessions.jsonl --cell "$cell" --output "$base/runtime_manifest.json"
  cleanup() { bash scripts/stop_vllm_server.sh --pid-path "$base/server.pid" --port "$port" || true; }
  trap cleanup EXIT
  bash scripts/run_vllm_server.sh --phase "r4-clock-$cell" --model-path "$DATA/models/Qwen3-8B" --served-model-name qwen3-8b --port "$port" --gpu-ids 0 --tensor-parallel-size 1 --dtype float16 --max-model-len 16384 --max-num-seqs 2 --gpu-memory-utilization .88 --log-path "$ROOT/logs/tsc_revision_r4/clock_${cell}_server.log" --pid-path "$base/server.pid"
  "$PY" scripts/tsc_revision_r2_prefix_smoke_logged.py --base-url "http://127.0.0.1:$port/v1" --model qwen3-8b --policy-hash "$CONTRACTKV_POLICY_HASH" --repeats 1 --output "$base/pre_measurement_control.jsonl" --evidence "$base/pre_measurement_full_ids.jsonl"
  "$PY" scripts/tsc_revision_r4_live_fixed.py --protocol configs/tsc_revision_r1r_validation_protocol_v1.json --catalog results/tsc_revision_r4/development_fit_v3/calibration_v1.json --previous-catalog configs/tsc_revision_r3_catalog_v1.json --profile balanced --sessions results/tsc_revision_r4/clock_smoke_v1/sessions.jsonl --arrival-trace results/tsc_revision_r4/clock_smoke_v1/arrivals.json --model qwen3-8b --model-identity Qwen3-8B --study single-session --policy "$policy" --base-url "http://127.0.0.1:$port/v1" --cell-id "$cell" --policy-hash "$CONTRACTKV_POLICY_HASH" --repeat 1 --tenants-per-template 1 --output "$base/raw.jsonl" --summary "$base/summary.json" --metrics-events "$base/metrics.jsonl"
) done
echo R4_CLOCK_SMOKE_V1_COMPLETE
