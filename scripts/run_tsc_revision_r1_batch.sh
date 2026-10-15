#!/usr/bin/env bash
# Whole-cell checkpoints permit resuming only complete fresh-process cells.
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
cd "$ROOT"
mkdir -p logs/tsc_revision_r1 results/tsc_revision_r1
exec 9>logs/tsc_revision_r1/batch.lock
flock -n 9 || { echo "Revision batch already owns this workspace"; exit 8; }
EXPECTED_PROTOCOL=3e0b31592b7e0ec08931f6fa0be8baa51c79e72463983078ada3b82f1f06a2ad
[[ $(sha256sum configs/tsc_major_revision_r1_protocol.json | awk '{print $1}') == "$EXPECTED_PROTOCOL" ]]

cell_complete() {
  local experiment=$1 model=$2 policy=$3 repeat=$4 budget=$5
  local path="results/tsc_revision_r1/cells/${experiment}_${model}_r${repeat}_${policy}_b${budget}/summary.json"
  [[ -s "$path" ]] || return 1
  "$PY" -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d["status"]=="complete" and d["future_requests"]==d["expected_future_requests"] and d["token_evidence_requests"]==d["future_requests"] and d["metric_join_requests"]==d["future_requests"]' "$path"
}

run_snapshot() {
  local snapshot
  mkdir -p "$ROOT/logs/tsc_revision_r1/runner_snapshots"
  snapshot=$(mktemp "$ROOT/logs/tsc_revision_r1/runner_snapshots/cell.XXXXXX.sh")
  cp scripts/run_tsc_revision_r1_cell.sh "$snapshot"
  bash "$snapshot" "$@"
}

run_pair() {
  local experiment=$1 model=$2 repeat=$3 sessions=$4 budget=$5
  local raw_gpu=$(( (repeat + 1) % 2 )) contract_gpu=$(( repeat % 2 ))
  local p0=0 p1=0
  # A partial attempt is evidence to inspect, never silently reused or deleted.
  if ! cell_complete "$experiment" "$model" raw-order "$repeat" "$budget"; then
    run_snapshot "$experiment" "$model" raw-order "$repeat" "$raw_gpu" 9830 "$sessions" "$budget" & p0=$!
  fi
  if ! cell_complete "$experiment" "$model" contractkv "$repeat" "$budget"; then
    run_snapshot "$experiment" "$model" contractkv "$repeat" "$contract_gpu" 9840 "$sessions" "$budget" & p1=$!
  fi
  local failed=0
  if [[ $p0 -ne 0 ]]; then wait "$p0" || failed=1; fi
  if [[ $p1 -ne 0 ]]; then wait "$p1" || failed=1; fi
  [[ $failed -eq 0 ]] || { echo "PAIR_FAILED $experiment $model $repeat $budget"; exit 31; }
  echo "PAIR_COMPLETE $experiment $model $repeat $budget $(date -u +%FT%TZ)"
}

COMMON="$ROOT/results/tsc_revision_r1/inputs/hotpot_heldout_sessions_v1.jsonl"
QUALITY="$ROOT/results/tsc_revision_r1/inputs/free_generation_sessions_v1.jsonl"
for model in qwen mistral llama; do
  for repeat in 1 2 3; do run_pair common-hotpot "$model" "$repeat" "$COMMON" 0; done
done
echo COMMON_HOTPOT_MATRIX_COMPLETE
for budget in 0 512; do
  for model in qwen mistral llama; do
    for repeat in 1 2 3; do run_pair free-generation "$model" "$repeat" "$QUALITY" "$budget"; done
  done
done
echo FREE_GENERATION_MATRIX_COMPLETE
echo MAIN_REVISION_MATRICES_COMPLETE
