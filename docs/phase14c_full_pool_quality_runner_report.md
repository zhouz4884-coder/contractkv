# Phase 14C Full-Pool Quality Runner Report

## Purpose

Phase 14C now has a full-pool QC feature file and a `1074`-job raw/CAPOSC
quality manifest. This step adds the resumable runner that turns those jobs
into paired fresh Qwen3-8B quality labels.

This report covers runner readiness and a small live smoke test. It does not
claim that the full-pool QC gate has passed the final false-safe threshold.

## Runner

```text
scripts/phase14c_run_full_pool_quality_jobs.py
```

The runner:

```text
loads the 8T full-pool JSONL
loads the job manifest
skips existing job_id rows in the raw output
runs OpenAI-compatible stream requests against vLLM
writes append-only raw JSONL rows
builds paired raw/CAPOSC quality labels
summarizes false-safe, fallback, unsafe-caught, and safe-coverage metrics
```

Default output paths:

```text
results/end_to_end/phase14c_full_pool_quality_raw_v0.jsonl
results/end_to_end/phase14c_full_pool_quality_labels_v0.csv
results/end_to_end/phase14c_full_pool_qc_calibration_summary_v0.csv
```

## Full Run Command

Run on the server:

```bash
ROOT=/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv
PY=/home/user/miniconda3/envs/contractkv-cu128/bin/python
cd "$ROOT"

$PY scripts/phase14c_run_full_pool_quality_jobs.py \
  --full-pool "$ROOT/results/workload/phase14d_full_pool_v0.jsonl" \
  --jobs "$ROOT/results/end_to_end/phase14c_full_pool_quality_jobs_v0.jsonl" \
  --features "$ROOT/results/end_to_end/phase14c_full_pool_qc_features_v0.csv" \
  --base-url http://localhost:8001/v1 \
  --model qwen3-8b \
  --max-tokens 96 \
  --timeout 240
```

The command is safe to rerun. It resumes by skipping `job_id` values that
already exist in `phase14c_full_pool_quality_raw_v0.jsonl`.

## Live Smoke

Server endpoint:

```text
http://localhost:8001/v1
model: qwen3-8b
```

Smoke command:

```bash
$PY scripts/phase14c_run_full_pool_quality_jobs.py \
  --full-pool "$ROOT/results/workload/phase14d_full_pool_v0.jsonl" \
  --jobs "$ROOT/results/end_to_end/phase14c_full_pool_quality_jobs_v0.jsonl" \
  --features "$ROOT/results/end_to_end/phase14c_full_pool_qc_features_v0.csv" \
  --base-url http://localhost:8001/v1 \
  --model qwen3-8b \
  --max-jobs 4 \
  --max-tokens 64 \
  --timeout 240 \
  --raw-output "$ROOT/results/end_to_end/phase14c_full_pool_quality_raw_smoke.jsonl" \
  --labels-output "$ROOT/results/end_to_end/phase14c_full_pool_quality_labels_smoke.csv" \
  --summary-output "$ROOT/results/end_to_end/phase14c_full_pool_qc_calibration_summary_smoke.csv"
```

Smoke result:

```text
new_rows=4
total_rows=4
paired_labels=2
```

The smoke summary contains:

```text
all: requests=2, labeled_pairs=2, unsafe_requests=0, fallback_rate=0.0,
     false_safe_rate=0.0, safe_optimization_coverage=1.0
```

This is execution-path evidence only. The sample is intentionally too small to
support a paper claim.

## Next Gate

The next required step is to run all `1074` jobs, then evaluate the final
Phase 14C gate against the objective:

```text
false-safe rate <= 2%
safe optimization coverage >= 50%
no significant quality drop vs raw
```

Only after that gate passes should QC-CAPOSC enter the Phase 14D live-serving
main comparison.
