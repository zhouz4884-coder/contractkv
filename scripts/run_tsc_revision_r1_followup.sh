#!/usr/bin/env bash
# Live zero-slack service and guard probes follow the primary paired matrices.
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
DATA="${CONTRACTKV_DISK_ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
cd "$ROOT"
main_pid=$(cat logs/tsc_revision_r1/batch.pid)
while ps -p "$main_pid" -o stat= 2>/dev/null | grep -qv '^ *Z'; do sleep 30; done
grep -q MAIN_REVISION_MATRICES_COMPLETE logs/tsc_revision_r1/batch.log || { echo "Main matrix needs inspection"; exit 12; }
SOURCE="$ROOT/third_party/vllm-contractkv-tsc-r1"
export PYTHONPATH="$SOURCE:$ROOT${PYTHONPATH:+:$PYTHONPATH}" PYTHON_BIN="$PY" VLLM_USE_V1=1
export TMPDIR="$DATA/tmp/contractkv-r1"
export HF_HOME="$DATA/datasets/hf_cache"
export CONTRACTKV_POLICY_HASH="$(sha256sum configs/tsc_major_revision_r1_protocol.json | awk '{print $1}')"
export CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000 CONTRACTKV_MAX_DEGRADATION=1000000000
export CONTRACTKV_SHADOW_QUANTUM=32 CONTRACTKV_SHADOW_ROUND_TOKENS=32
export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1 CONTRACTKV_PREFIX_CONCURRENT_SNAPSHOTS=1
export VLLM_STARTUP_POLLS=360 EXTRA_VLLM_ARGS="--enable-prefix-caching --host 127.0.0.1"

run_cell() (
  set -euo pipefail
  local model=$1 repeat=$2 policy=$3 gpu=$4 port=$5
  local cell="zero-slack_${model}_r${repeat}_${policy}"
  local dir="$ROOT/results/tsc_revision_r1/service/$cell"
  if [[ -s "$dir/summary.jsonl" ]]; then echo "SKIP_COMPLETE $cell"; return; fi
  [[ ! -e "$dir/raw.jsonl" ]] || { echo "Partial service cell requires inspection: $cell"; exit 41; }
  mkdir -p "$dir"
  case "$model" in
    qwen) model_path="$DATA/models/Qwen3-8B"; identity=Qwen3-8B; served=qwen3-8b ;;
    mistral) model_path="$DATA/models/Mistral-7B-Instruct-v0.3"; identity=Mistral-7B-Instruct-v0.3; served=mistral7b ;;
  esac
  export CONTRACTKV_PREFIX_METRICS_LOG="$dir/metrics.jsonl"
  export VLLM_CACHE_ROOT="$ROOT/cache/tsc_revision_r1/$cell/vllm"
  export TRITON_CACHE_DIR="$ROOT/cache/tsc_revision_r1/$cell/triton"
  export TORCHINDUCTOR_CACHE_DIR="$ROOT/cache/tsc_revision_r1/$cell/torchinductor"
  "$PY" scripts/tsc_revision_cell_manifest.py --root "$ROOT" --source "$SOURCE" --model "$model_path" \
    --sessions results/tsc_revision_r1/inputs/service_sessions_v1.jsonl --output "$dir/cell_manifest.json" \
    --cell "$cell" --gpu "$gpu" --budget 0
  cleanup() { bash scripts/stop_vllm_server.sh --pid-path "$dir/server.pid" --port "$port" || true; }
  trap cleanup EXIT
  bash scripts/run_vllm_server.sh --phase "$cell" --model-path "$model_path" --served-model-name "$served" \
    --port "$port" --gpu-ids "$gpu" --tensor-parallel-size 1 --dtype float16 --max-model-len 16384 \
    --max-num-seqs 2 --gpu-memory-utilization .88 --log-path "$ROOT/logs/tsc_revision_r1/${cell}_server.log" --pid-path "$dir/server.pid"
  "$PY" scripts/tsc_revision_zero_slack_live.py --sessions results/tsc_revision_r1/inputs/service_sessions_v1.jsonl \
    --protocol "results/tsc_revision_r1/inputs/service_${model}_protocol_v1.json" --tokenizer "$model_path" \
    --model-identity "$identity" --policy "$policy" --repeat "$repeat" --cell-id "$cell" \
    --base-url "http://127.0.0.1:$port/v1" --model "$served" --policy-hash "$CONTRACTKV_POLICY_HASH" \
    --qualification-hash "$CONTRACTKV_POLICY_HASH" --arrival-rate-rps 1.6 --seed 10672026 \
    --metrics-events "$dir/metrics.jsonl" --raw-output "$dir/raw.jsonl" --registration-output "$dir/registration.jsonl" \
    --summary-output "$dir/summary.jsonl" --slo-buckets-ms 500,1000,1500,3000
  if [[ "$model" == qwen && "$policy" == D2-template-contractkv && $repeat -eq 1 ]]; then
    "$PY" scripts/tsc_revision_guard_probe.py --base-url "http://127.0.0.1:$port/v1" --model "$served" \
      --policy-hash "$CONTRACTKV_POLICY_HASH" --output "$ROOT/results/tsc_revision_r1/guard_probe_qwen_v1.jsonl"
  fi
)
for repeat in 1 2 3; do
  for policy in D0-native-apc D1-frozen-safe D2-template-contractkv; do
    run_cell qwen "$repeat" "$policy" $((repeat % 2)) 9850 & p0=$!
    run_cell mistral "$repeat" "$policy" $(((repeat + 1) % 2)) 9860 & p1=$!
    failed=0; wait "$p0" || failed=1; wait "$p1" || failed=1
    [[ $failed -eq 0 ]] || exit 31
    echo "ZERO_SLACK_PAIR_COMPLETE $repeat $policy"
  done
done
echo ZERO_SLACK_AND_GUARD_COMPLETE
