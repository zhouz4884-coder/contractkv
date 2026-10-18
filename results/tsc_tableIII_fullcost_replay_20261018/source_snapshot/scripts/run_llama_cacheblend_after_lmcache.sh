#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
cd "$ROOT"

if [[ "${WAIT_FOR_SERIAL:-1}" == 1 ]]; then
  while pgrep -f 'run_llama_lmcache_baselines_serial.sh' >/dev/null; do sleep 30; done
  while pgrep -f 'vllm.entrypoints.openai.api_server.*--port 9300' >/dev/null; do sleep 15; done
  sleep 30
fi
for repeat in 1 2 3 4 5; do
  CELLS="cacheblend:$repeat" LEFT_GPU="${CACHEBLEND_GPU:-1}" LEFT_PORT_BASE="${CACHEBLEND_PORT_BASE:-9300}" \
    bash scripts/run_llama_lmcache_baselines.sh
done
echo LLAMA_CACHEBLEND_SERIAL_COMPLETE
