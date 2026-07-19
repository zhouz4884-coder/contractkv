#!/usr/bin/env bash
# End-to-end TSC service-evaluation orchestration after the capacity pilot.
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
LOG="$ROOT/logs/tsc_service"; mkdir -p "$LOG"; cd "$ROOT"

if [[ -f "$LOG/pilot.pid" ]]; then
  pilot_pid=$(cat "$LOG/pilot.pid")
  while kill -0 "$pilot_pid" 2>/dev/null; do sleep 30; done
fi
pilot_cells=$(find "$ROOT/results/tsc_service/open_loop_cells" -path '*_r0_*' -name summary.jsonl -type f | wc -l)
[[ "$pilot_cells" -eq 10 ]] || { echo "pilot incomplete: cells=$pilot_cells" >&2; exit 31; }
"$PY" - <<'PY'
import glob, json
paths = glob.glob('results/tsc_service/open_loop_cells/*_r0_*/summary.jsonl')
assert len(paths) == 10, len(paths)
for path in paths:
    rows = [json.loads(line) for line in open(path)]
    assert rows, path
    assert all(row['quality_sanity_rate'] == 1.0 for row in rows), path
    assert all(row['metric_join_rate'] == 1.0 for row in rows), path
print('TSC_PILOT_CORRECTNESS_PASS')
PY
"$PY" scripts/summarize_tsc_service_extension.py --root "$ROOT/results/tsc_service" \
  --docs-output "$ROOT/docs/tsc_service_evaluation_extension_report.md" --allow-partial
read -r QBASE MBASE < <("$PY" - <<'PY'
import csv
rows={r['model']:r for r in csv.DictReader(open('results/tsc_service/open_loop_pilot_capacity_v0.csv'))}
print(rows['qwen']['frozen_baseline_capacity_rps'], rows['mistral']['frozen_baseline_capacity_rps'])
PY
)
"$PY" -c "assert float('$QBASE') > 0 and float('$MBASE') > 0"
printf 'QWEN_BASELINE_RPS=%s\nMISTRAL_BASELINE_RPS=%s\n' "$QBASE" "$MBASE" > "$ROOT/results/tsc_service/frozen_capacity_rates_v0.env"

"$PY" scripts/build_tsc_service_locality_traces.py \
  --sessions "$ROOT/results/tsc_service/tsc_service_sessions_v0.jsonl" \
  --output-dir "$ROOT/results/tsc_service"
for templates in 5 25 50; do
  "$PY" scripts/build_tsc_residency_arrivals.py \
    --sessions "$ROOT/results/tsc_service/tsc_service_sessions_templates_t${templates}_v0.jsonl" \
    --base-arrivals "$ROOT/results/tsc_service/tsc_service_arrivals_v0.jsonl" \
    --output-dir "$ROOT/results/tsc_service" --template-count "$templates"
done
env PROFILE=pilot bash scripts/run_tsc_service_locality_sweep.sh > "$LOG/locality_pilot.log" 2>&1
env PROFILE=full bash scripts/run_tsc_service_locality_sweep.sh > "$LOG/locality_full.log" 2>&1
bash scripts/run_tsc_residency_sweep.sh > "$LOG/residency.log" 2>&1

env PROFILE=full QWEN_BASELINE_RPS="$QBASE" MISTRAL_BASELINE_RPS="$MBASE" \
  bash scripts/run_tsc_open_loop.sh > "$LOG/full_open_loop.log" 2>&1
bash scripts/run_tsc_verification_economics.sh > "$LOG/economics.log" 2>&1
bash scripts/run_tsc_service_lifecycle.sh > "$LOG/lifecycle.log" 2>&1
env PROFILE=all bash scripts/run_tsc_multi_tenant.sh > "$LOG/multi_tenant.log" 2>&1
"$PY" scripts/summarize_tsc_service_extension.py --root "$ROOT/results/tsc_service" \
  --docs-output "$ROOT/docs/tsc_service_evaluation_extension_report.md"
"$PY" scripts/render_tsc_service_reports.py --root "$ROOT/results/tsc_service" --docs "$ROOT/docs"
echo TSC_SERVICE_EXTENSION_COMPLETE
