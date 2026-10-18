#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
cd "$ROOT"
while pgrep -f 'run_llama_cacheblend_after_lmcache.sh' >/dev/null; do sleep 30; done
while pgrep -f 'vllm.entrypoints.openai.api_server.*--port 9300' >/dev/null; do sleep 15; done
sleep 30
bash scripts/run_llama_lmcache_baselines_serial.sh
echo LLAMA_LMCACHE_RESUME_COMPLETE
