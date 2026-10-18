#!/usr/bin/env bash
set -euo pipefail

OUTPUT_PATH="${1:?usage: monitor_gpu.sh OUTPUT_PATH [INTERVAL_SECONDS]}"
INTERVAL_SECONDS="${2:-0.5}"

mkdir -p "$(dirname "$OUTPUT_PATH")"
printf 'timestamp,index,memory.used [MiB],memory.total [MiB],utilization.gpu [%%],utilization.memory [%%]\n' > "$OUTPUT_PATH"

while true; do
  nvidia-smi \
    --query-gpu=timestamp,index,memory.used,memory.total,utilization.gpu,utilization.memory \
    --format=csv,noheader >> "$OUTPUT_PATH"
  sleep "$INTERVAL_SECONDS"
done
