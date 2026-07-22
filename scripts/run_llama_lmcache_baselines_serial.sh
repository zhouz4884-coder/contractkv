#!/usr/bin/env bash
set -uo pipefail

ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
CELLS_LIST="${CELLS_LIST:-lmcache:1 blendraw:1 lmcache:2 blendraw:2 lmcache:3 blendraw:3 lmcache:4 blendraw:4 lmcache:5 blendraw:5}"
cd "$ROOT"

while pgrep -f 'vllm.entrypoints.openai.api_server.*--port 9300' >/dev/null; do sleep 15; done
sleep 15
for cell in $CELLS_LIST; do
  echo "SERIAL_CELL_START $cell"
  CELLS="$cell" LEFT_GPU=1 LEFT_PORT_BASE=9300 bash scripts/run_llama_lmcache_baselines.sh
  rc=$?
  echo "SERIAL_CELL_END $cell rc=$rc"
  if (( rc != 0 )); then
    echo "SERIAL_CELL_FAILED $cell" >&2
    exit "$rc"
  fi
done
echo LLAMA_LMCACHE_SERIAL_COMPLETE
