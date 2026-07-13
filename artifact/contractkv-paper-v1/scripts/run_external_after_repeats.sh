#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
REPEAT_LOG="$ROOT/logs/submission_repeats/driver.log"
INSTALL_LOG="$ROOT/logs/external_baseline/install.log"

until grep -q 'SUBMISSION_REPEATS_COMPLETE' "$REPEAT_LOG" 2>/dev/null; do
  if ! pgrep -f 'scripts/run_submission_repeats.sh' >/dev/null; then
    echo "submission repeat driver exited before completion" >&2
    exit 41
  fi
  sleep 20
done

until grep -q 'SGLANG_EXTERNAL_ENV_READY' "$INSTALL_LOG" 2>/dev/null; do
  if ! pgrep -f 'scripts/install_sglang_external_baseline.sh' >/dev/null; then
    echo "SGLang install exited before readiness" >&2
    exit 42
  fi
  sleep 20
done

while nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | grep -q '[0-9]'; do
  sleep 10
done

cd "$ROOT"
bash scripts/run_external_sglang_baseline.sh
