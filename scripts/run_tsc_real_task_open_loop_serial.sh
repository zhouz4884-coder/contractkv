#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
CELLS_LIST="${CELLS_LIST:-D0-native-apc:1 D1-frozen-safe:1 D2-template-contractkv:1 D0-native-apc:2 D1-frozen-safe:2 D2-template-contractkv:2 D0-native-apc:3 D1-frozen-safe:3 D2-template-contractkv:3 D0-native-apc:4 D1-frozen-safe:4 D2-template-contractkv:4 D0-native-apc:5 D1-frozen-safe:5 D2-template-contractkv:5}"
cd "$ROOT"

while pgrep -f 'vllm.entrypoints.openai.api_server.*--port 9100' >/dev/null; do sleep 15; done
sleep 15
for cell in $CELLS_LIST; do
  CELLS="$cell" bash scripts/run_tsc_real_task_open_loop.sh
done
echo TSC_REAL_TASK_SERIAL_COMPLETE
