#!/usr/bin/env bash
set -euo pipefail

ROOT="${CONTRACTKV_V100_ROOT:-/data/home/${USER}/contractkv_v100}"
ENV="$ROOT/env/contractkv-v100-cu121"
MODELSCOPE="$ENV/bin/modelscope"

if [[ ! -x "$MODELSCOPE" ]]; then
  echo "Missing ModelScope CLI: $MODELSCOPE" >&2
  exit 2
fi

mkdir -p "$ROOT/models" "$ROOT/logs/downloads" "$ROOT/hf_cache/modelscope"
export MODELSCOPE_CACHE="$ROOT/hf_cache/modelscope"

start_download() {
  local label="$1"
  local model_id="$2"
  local target="$ROOT/models/$label"
  local pid_file="$ROOT/logs/downloads/${label}.pid"
  local log_file="$ROOT/logs/downloads/${label}.log"

  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    echo "$label already running: pid $(cat "$pid_file")"
    return
  fi

  if [[ -f "$target/config.json" ]] && find "$target" -maxdepth 1 -name '*.safetensors' -print -quit | grep -q .; then
    echo "$label appears complete: $target"
    return
  fi

  mkdir -p "$target"
  nohup "$MODELSCOPE" download --model "$model_id" --local-dir "$target" --max-workers 8 \
    > "$log_file" 2>&1 < /dev/null &
  echo $! > "$pid_file"
  echo "Started $label: pid $(cat "$pid_file"), log $log_file"
}

start_download "qwen3-32b" "Qwen/Qwen3-32B"
start_download "mistral-small-24b-instruct-2501" "mistralai/Mistral-Small-24B-Instruct-2501"
start_download "llama-3.1-70b-instruct" "LLM-Research/Meta-Llama-3.1-70B-Instruct"
