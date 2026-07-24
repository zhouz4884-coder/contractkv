#!/usr/bin/env bash
set -euo pipefail

DISK="${CONTRACTKV_DISK_ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9}"
ROOT="${ROOT:-$DISK/VLAtest/contractkv}"
ENV_PREFIX="${ENV_PREFIX:-$DISK/envs/specserve-vllm0251}"
CUDA_TOOLKIT="${CUDA_TOOLKIT:-$DISK/envs/cuda-nvcc-12.8}"
MODEL="${MODEL:-$DISK/models/Qwen3-8B}"
MODEL_NAME="${MODEL_NAME:-qwen3-8b-v0251}"
PORT="${PORT:-9251}"
FRESH_REPEATS="${FRESH_REPEATS:-3}"
CASES_PER_SOURCE="${CASES_PER_SOURCE:-5}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-20000}"
MAX_NUM_SEQS="${MAX_NUM_SEQS:-1}"
CONTEXT_TARGET_TOKENS="${CONTEXT_TARGET_TOKENS:-18000}"
OUT="$ROOT/results/appendix/vllm_025"
LOG="$DISK/logs/contractkv_appendix/vllm_025"

mkdir -p "$OUT" "$LOG" "$DISK/cache/contractkv-runtime/flashinfer-v0251"
cd "$ROOT"

export ENV_PREFIX
export PYTHON_BIN="$ENV_PREFIX/bin/python"
export CONTRACTKV_DISK_ROOT="$DISK"
export CUDA_HOME="$CUDA_TOOLKIT"
export PATH="$CUDA_HOME/bin:$PATH"
export FLASHINFER_WORKSPACE_BASE="$DISK/cache/contractkv-runtime/flashinfer-v0251"
# The 3090 host's /usr/local/cuda points to CUDA 11.2. Disabling the optional
# FlashInfer sampler avoids a JIT dependency on that stale system toolkit.
export VLLM_USE_FLASHINFER_SAMPLER=0
export EXTRA_VLLM_ARGS="--enable-prefix-caching"

"$PYTHON_BIN" scripts/audit_vllm_version_compatibility.py \
  --output "$OUT/vllm_025_hook_portability_audit.json"

raw_files=()
for repeat in $(seq 1 "$FRESH_REPEATS"); do
  tag="vllm0251-qwen3-8b-r${repeat}"
  server_log="$LOG/${tag}.log"
  pid_path="$LOG/${tag}.pid"
  raw_output="$OUT/${tag}_raw.jsonl"
  repeat_summary="$OUT/${tag}_summary.csv"
  raw_files+=("$raw_output")

  cleanup() {
    bash scripts/stop_vllm_server.sh --pid-path "$pid_path" --port "$PORT" \
      >/dev/null 2>&1 || true
  }
  trap cleanup EXIT
  cleanup

  bash scripts/run_vllm_server.sh \
    --phase appendix-vllm0251 \
    --model-path "$MODEL" \
    --served-model-name "$MODEL_NAME" \
    --port "$PORT" \
    --gpu-ids 0 \
    --tensor-parallel-size 1 \
    --dtype float16 \
    --max-model-len "$MAX_MODEL_LEN" \
    --max-num-seqs "$MAX_NUM_SEQS" \
    --gpu-memory-utilization .88 \
    --log-path "$server_log" \
    --pid-path "$pid_path"

  "$PYTHON_BIN" scripts/vllm_025_structural_relevance_audit.py \
    --base-url "http://127.0.0.1:$PORT/v1" \
    --model "$MODEL_NAME" \
    --model-path "$MODEL" \
    --samples results/datasets/sample_prompts.jsonl \
    --fresh-repeat "$repeat" \
    --cases-per-source "$CASES_PER_SOURCE" \
    --context-target-tokens "$CONTEXT_TARGET_TOKENS" \
    --max-tokens 64 \
    --quality-threshold .5 \
    --timeout 300 \
    --server-log-path "$server_log" \
    --raw-output "$raw_output" \
    --summary-output "$repeat_summary"

  cleanup
  trap - EXIT
done

"$PYTHON_BIN" scripts/vllm_025_structural_relevance_audit.py \
  --summarize-input "${raw_files[@]}" \
  --summary-output "$OUT/vllm_025_structural_audit_summary.csv"

"$PYTHON_BIN" - "${raw_files[@]}" "$OUT/vllm_025_structural_audit_raw.jsonl" <<'PY'
import json
import pathlib
import sys

inputs = [pathlib.Path(value) for value in sys.argv[1:-1]]
output = pathlib.Path(sys.argv[-1])
with output.open("w", encoding="utf-8", newline="\n") as sink:
    for path in inputs:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                json.loads(line)
                sink.write(line + "\n")
PY

echo "VLLM_025_APPENDIX_AUDIT_COMPLETE out=$OUT"
