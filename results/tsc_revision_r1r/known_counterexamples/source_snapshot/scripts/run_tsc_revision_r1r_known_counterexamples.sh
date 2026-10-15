#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
DATA=/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9
PY=/home/user/miniconda3/envs/contractkv-cu128/bin/python
cd "$ROOT"
while ! grep -q R1R_RAW_EVIDENCE_FINALIZED logs/tsc_revision_r1r/finalize_v1.log; do
  if ! kill -0 2343437 2>/dev/null; then echo 'Primary evidence finalizer stopped before completion'; exit 88; fi
  sleep 30
done
sha256sum -c results/tsc_revision_r1r/known_counterexamples/source_checksums.sha256
export PYTHONPATH="$ROOT/third_party/vllm-contractkv-tsc-r1r-slice:$ROOT" PYTHON_BIN="$PY" VLLM_USE_V1=1
export TMPDIR="$DATA/tmp/contractkv-r1r" HF_HOME="$DATA/datasets/hf_cache"
export CONTRACTKV_POLICY_HASH="$(sha256sum results/tsc_revision_r1r/known_counterexamples/freeze_v1.json | awk '{print $1}')"
export CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000 CONTRACTKV_MAX_DEGRADATION=1000000000
export CONTRACTKV_SHADOW_CHUNK_TOKENS=128 CONTRACTKV_SHADOW_ROUND_TOKENS=128
export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1
export EXTRA_VLLM_ARGS="--enable-prefix-caching --host 127.0.0.1" VLLM_STARTUP_POLLS=360
run_model() (
  model=$1 gpu=$2 port=$3
  case "$model" in
    qwen) path="$DATA/models/Qwen3-8B"; served=qwen3-8b; identity=Qwen3-8B ;;
    mistral) path="$DATA/models/Mistral-7B-Instruct-v0.3"; served=mistral7b; identity=Mistral-7B-Instruct-v0.3 ;;
    llama) path="$DATA/models/Llama-3.1-8B-Instruct"; served=llama31-8b; identity=Llama-3.1-8B-Instruct ;;
  esac
  base="$ROOT/results/tsc_revision_r1r/known_counterexamples/$model"; mkdir -p "$base"
  export CONTRACTKV_PREFIX_METRICS_LOG="$base/metrics.jsonl"
  export VLLM_CACHE_ROOT="$ROOT/cache/tsc_revision_r1r/known-$model/vllm"
  export TRITON_CACHE_DIR="$ROOT/cache/tsc_revision_r1r/known-$model/triton"
  export TORCHINDUCTOR_CACHE_DIR="$ROOT/cache/tsc_revision_r1r/known-$model/inductor"
  cleanup() { bash scripts/stop_vllm_server.sh --pid-path "$base/server.pid" --port "$port" || true; }
  trap cleanup EXIT
  bash scripts/run_vllm_server.sh --phase "known-$model" --model-path "$path" --served-model-name "$served" \
    --port "$port" --gpu-ids "$gpu" --tensor-parallel-size 1 --dtype float16 --max-model-len 16384 \
    --max-num-seqs 2 --gpu-memory-utilization .88 --log-path "$ROOT/logs/tsc_revision_r1r/known-${model}_server.log" --pid-path "$base/server.pid"
  for policy in raw-order legacy-unbound query-prefix; do
    dir="$base/$policy"; mkdir -p "$dir"
    [[ ! -e "$dir/raw.jsonl" ]] || exit 41
    if [[ "$policy" == legacy-unbound ]]; then
      "$PY" scripts/tsc_revision_live.py --protocol configs/tsc_revision_r1r_validation_protocol_v1.json --experiment free-generation \
        --sessions "results/tsc_revision_r1r/known_counterexamples/inputs/${model}_sessions_v1.jsonl" --model "$served" --model-identity "$identity" \
        --policy contractkv --base-url "http://127.0.0.1:$port/v1" --cell-id "known-${model}-${policy}" --policy-hash "$CONTRACTKV_POLICY_HASH" \
        --repeat 1 --output "$dir/raw.jsonl" --summary "$dir/summary.json" --metrics-events "$base/metrics.jsonl"
    else
      "$PY" scripts/tsc_revision_r1r_live.py --protocol configs/tsc_revision_r1r_validation_protocol_v1.json \
        --sessions "results/tsc_revision_r1r/known_counterexamples/inputs/${model}_sessions_v1.jsonl" --model "$served" --model-identity "$identity" \
        --study known-counterexample --policy "$policy" --base-url "http://127.0.0.1:$port/v1" --cell-id "known-${model}-${policy}" --policy-hash "$CONTRACTKV_POLICY_HASH" \
        --repeat 1 --output "$dir/raw.jsonl" --summary "$dir/summary.json" --metrics-events "$base/metrics.jsonl"
    fi
  done
)
run_model qwen 0 9880 & p0=$!
run_model mistral 1 9881 & p1=$!
failed=0; wait "$p0" || failed=1; wait "$p1" || failed=1
[[ "$failed" == 0 ]] || exit 31
run_model llama 0 9880
"$PY" scripts/tsc_revision_r1r_known_summary.py --root results/tsc_revision_r1r/known_counterexamples
echo R1R_KNOWN_COUNTEREXAMPLES_COMPLETE
