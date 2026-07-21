#!/usr/bin/env bash
set -euo pipefail

ROOT="${CONTRACTKV_V100_ROOT:-/data/home/${USER}/contractkv_v100}"
JOB_ID="$(qsub "$ROOT/pbs/00_preflight_gpu2.pbs")"
printf 'Submitted V100 preflight: %s\n' "$JOB_ID"
