#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
cd "$ROOT"
until grep -q 'EXTERNAL_SGLANG_BASELINE_COMPLETE' "$ROOT/logs/external_baseline/driver.log" 2>/dev/null; do
  if ! pgrep -f 'scripts/run_external_after_repeats.sh|scripts/run_external_sglang_baseline.sh' >/dev/null; then
    echo "external SGLang driver exited before completion" >&2
    exit 41
  fi
  sleep 20
done
while nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | grep -q '[0-9]'; do sleep 10; done
bash scripts/run_llama_qualified_replay.sh
while nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | grep -q '[0-9]'; do sleep 10; done
bash scripts/run_physical_dedup_submission.sh
echo REMAINING_SUBMISSION_EXPERIMENTS_COMPLETE
