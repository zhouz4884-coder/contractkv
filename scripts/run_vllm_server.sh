#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${ENV_NAME:-contractkv-cu128}"
CONTRACTKV_DISK_ROOT="${CONTRACTKV_DISK_ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9}"
ENV_PREFIX="${ENV_PREFIX:-${CONTRACTKV_DISK_ROOT}/envs/contractkv-cu128}"
CONDA_SH="${CONDA_SH:-$HOME/miniconda3/etc/profile.d/conda.sh}"
RUNTIME_TMP_REAL="${RUNTIME_TMP_REAL:-${CONTRACTKV_DISK_ROOT}/tmp/contractkv-runtime}"
RUNTIME_TMP_LINK="${RUNTIME_TMP_LINK:-/tmp/contractkv-runtime}"
TMPDIR="${TMPDIR:-${RUNTIME_TMP_LINK}}"
XDG_CACHE_HOME="${XDG_CACHE_HOME:-${CONTRACTKV_DISK_ROOT}/cache/contractkv-runtime/xdg}"
HF_HOME="${HF_HOME:-${CONTRACTKV_DISK_ROOT}/cache/contractkv-runtime/huggingface}"
HF_HUB_CACHE="${HF_HUB_CACHE:-${HF_HOME}/hub}"
TRANSFORMERS_CACHE="${TRANSFORMERS_CACHE:-${HF_HOME}/transformers}"
TORCH_HOME="${TORCH_HOME:-${CONTRACTKV_DISK_ROOT}/cache/contractkv-runtime/torch}"
TRITON_CACHE_DIR="${TRITON_CACHE_DIR:-${CONTRACTKV_DISK_ROOT}/cache/contractkv-runtime/triton}"
VLLM_CACHE_ROOT="${VLLM_CACHE_ROOT:-${CONTRACTKV_DISK_ROOT}/cache/contractkv-runtime/vllm}"
EXTRA_VLLM_ARGS="${EXTRA_VLLM_ARGS:-}"
PHASE=""
MODEL_PATH=""
SERVED_MODEL_NAME=""
PORT=""
GPU_IDS="0"
TP_SIZE="1"
DTYPE="float16"
MAX_MODEL_LEN=""
MAX_NUM_SEQS=""
GPU_MEMORY_UTILIZATION=""
LOG_PATH=""
PID_PATH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --phase) PHASE="$2"; shift 2 ;;
    --model-path) MODEL_PATH="$2"; shift 2 ;;
    --served-model-name) SERVED_MODEL_NAME="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --gpu-ids) GPU_IDS="$2"; shift 2 ;;
    --tensor-parallel-size) TP_SIZE="$2"; shift 2 ;;
    --dtype) DTYPE="$2"; shift 2 ;;
    --max-model-len) MAX_MODEL_LEN="$2"; shift 2 ;;
    --max-num-seqs) MAX_NUM_SEQS="$2"; shift 2 ;;
    --gpu-memory-utilization) GPU_MEMORY_UTILIZATION="$2"; shift 2 ;;
    --log-path) LOG_PATH="$2"; shift 2 ;;
    --pid-path) PID_PATH="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$MODEL_PATH" || -z "$SERVED_MODEL_NAME" || -z "$PORT" || -z "$MAX_MODEL_LEN" || -z "$MAX_NUM_SEQS" || -z "$GPU_MEMORY_UTILIZATION" || -z "$LOG_PATH" ]]; then
  echo "Missing required arguments." >&2
  exit 2
fi

PID_PATH="${PID_PATH:-${LOG_PATH%.log}.pid}"
mkdir -p "$(dirname "$LOG_PATH")" "$(dirname "$PID_PATH")" "$RUNTIME_TMP_REAL" \
  "$XDG_CACHE_HOME" "$HF_HOME" "$HF_HUB_CACHE" "$TRANSFORMERS_CACHE" \
  "$TORCH_HOME" "$TRITON_CACHE_DIR" "$VLLM_CACHE_ROOT"
if [[ "$TMPDIR" == "$RUNTIME_TMP_LINK" && ! -e "$TMPDIR" ]]; then
  ln -s "$RUNTIME_TMP_REAL" "$TMPDIR"
fi
mkdir -p "$TMPDIR"
export TMPDIR XDG_CACHE_HOME HF_HOME HF_HUB_CACHE TRANSFORMERS_CACHE
export TORCH_HOME TRITON_CACHE_DIR VLLM_CACHE_ROOT

if command -v lsof >/dev/null 2>&1 && lsof -i ":${PORT}" >/dev/null 2>&1; then
  echo "Port ${PORT} is already in use." | tee -a "$LOG_PATH" >&2
  exit 10
fi

if [[ ! -f "$CONDA_SH" ]]; then
  echo "Conda activation script not found: $CONDA_SH" | tee -a "$LOG_PATH" >&2
  exit 11
fi

# shellcheck source=/dev/null
source "$CONDA_SH"
if [[ -x "$ENV_PREFIX/bin/python" ]]; then
  conda activate "$ENV_PREFIX"
else
  conda activate "$ENV_NAME"
fi

echo "phase=${PHASE}" > "$LOG_PATH"
echo "started_at=$(date -Iseconds)" >> "$LOG_PATH"
echo "model_path=${MODEL_PATH}" >> "$LOG_PATH"
echo "served_model_name=${SERVED_MODEL_NAME}" >> "$LOG_PATH"
echo "port=${PORT}" >> "$LOG_PATH"
echo "contractkv_disk_root=${CONTRACTKV_DISK_ROOT}" >> "$LOG_PATH"
echo "tmpdir=${TMPDIR}" >> "$LOG_PATH"
echo "xdg_cache_home=${XDG_CACHE_HOME}" >> "$LOG_PATH"
echo "vllm_cache_root=${VLLM_CACHE_ROOT}" >> "$LOG_PATH"
echo "extra_vllm_args=${EXTRA_VLLM_ARGS}" >> "$LOG_PATH"

EXTRA_ARGS_ARRAY=()
if [[ -n "$EXTRA_VLLM_ARGS" ]]; then
  # shellcheck disable=SC2206
  EXTRA_ARGS_ARRAY=($EXTRA_VLLM_ARGS)
fi

CUDA_VISIBLE_DEVICES="$GPU_IDS" nohup python -m vllm.entrypoints.openai.api_server \
  --model "$MODEL_PATH" \
  --served-model-name "$SERVED_MODEL_NAME" \
  --dtype "$DTYPE" \
  --tensor-parallel-size "$TP_SIZE" \
  --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION" \
  --max-model-len "$MAX_MODEL_LEN" \
  --max-num-seqs "$MAX_NUM_SEQS" \
  --port "$PORT" \
  "${EXTRA_ARGS_ARRAY[@]}" >> "$LOG_PATH" 2>&1 &

PID=$!
echo "$PID" > "$PID_PATH"
echo "pid=${PID}" >> "$LOG_PATH"

for _ in $(seq 1 180); do
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "vLLM process exited during startup. See $LOG_PATH" >&2
    exit 12
  fi
  if curl -fsS "http://127.0.0.1:${PORT}/v1/models" >/dev/null 2>&1; then
    echo "ready_at=$(date -Iseconds)" >> "$LOG_PATH"
    echo "READY pid=${PID} port=${PORT} log=${LOG_PATH}"
    exit 0
  fi
  sleep 2
done

echo "Timed out waiting for vLLM readiness. See $LOG_PATH" >&2
exit 13
