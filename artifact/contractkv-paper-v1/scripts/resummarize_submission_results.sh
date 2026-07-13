#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
OUT="$ROOT/results/submission_repeats"
cd "$ROOT"
repairs=(); cells=()
for model in qwen mistral; do
  for repeat in 1 2 3; do
    repairs+=(--input "$OUT/$model/repeat$repeat/contractkv-full.jsonl")
    cells+=(--cell "$model,$repeat,raw-order,$OUT/$model/repeat$repeat/raw-order.jsonl")
    cells+=(--cell "$model,$repeat,contractkv-full,$OUT/$model/repeat$repeat/contractkv-full.jsonl")
  done
done
"$PY" scripts/repair_submission_scope_telemetry.py "${repairs[@]}" \
  --manifest "$OUT/scope_telemetry_repair_manifest_v0.json"
"$PY" scripts/summarize_submission_repeats.py "${cells[@]}" --slo-ms 1500 \
  --raw-output "$OUT/submission_repeat_cells_v0.csv" \
  --paired-output "$OUT/submission_repeat_pairs_v0.csv" \
  --aggregate-output "$OUT/submission_repeat_aggregate_v0.csv" \
  --json-output "$OUT/submission_repeat_summary_v0.json"
