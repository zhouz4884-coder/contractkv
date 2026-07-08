# Phase 10.2B Real Quality Risk Summary

## Goal

Convert the Phase 10.2 real Qwen3-8B output matrix into a compact risk table:

```text
Risk(dataset, task, condition) = mean_quality_drop
```

Context-overflow failures are tracked separately as capacity failures, not model answer errors.

## Inputs

```text
results/hard_systems/real_quality_outputs_qwen3_8b_v0.jsonl
results/hard_systems/real_quality_matrix_qwen3_8b_v0.csv
```

Postprocess script:

```text
scripts/build_real_quality_risk_summary.py
```

## Outputs

```text
results/hard_systems/real_quality_risk_summary_qwen3_8b_v0.csv
results/hard_systems/context_overflow_cases_qwen3_8b_v0.csv
```

## Results

```text
risk summary rows: 42
context overflow rows: 24
successful model requests used for risk: 816
capacity failures separated from quality scoring: 24
```

The 24 overflow cases are HTTP 400 context-limit failures from vLLM and are concentrated in LongBench `narrativeqa`. They are not counted as wrong model answers.

## Risk Construction

For each `(dataset, task, condition)`:

```text
baseline_mean_score = mean score of successful full_context_baseline requests
mean_quality_drop = max(0, baseline_mean_score - condition_mean_score)
```

Rules:

1. Successful requests are used for real quality scoring.
2. HTTP 400 context overflow is written to `context_overflow_cases_qwen3_8b_v0.csv`.
3. Overflow is treated as capacity failure, not answer-quality failure.
4. LongBench `narrativeqa` should be analyzed as a 32K-safe subset when used later.
5. RepoBench boundary repair improvement is marked as a scoring artifact candidate.

## Key Observations

Representative real quality drops:

| Dataset | Task | Condition | Mean Quality Drop |
| --- | --- | --- | ---: |
| RULER | niah_single_1 | segment_eviction | 1.000000 |
| LongBench | hotpotqa | segment_eviction | 0.511438 |
| LongBench | hotpotqa | context_truncation | 0.463016 |
| RepoBench | python_repository_completion | segment_eviction | 0.154149 |
| RepoBench | python_repository_completion | context_truncation | 0.138985 |

RepoBench `boundary_repair` improves the proxy similarity score relative to baseline in v0, so it is labeled:

```text
scoring_artifact_candidate_boundary_repair_improves_similarity
```

## What This Enables

Phase 10.5 can use a real output-derived `Risk(s, a)` table instead of the earlier proxy ledger. Capacity failures remain available as a separate serving constraint.

## Boundaries

This postprocess does not rerun the 840 model requests. It cleans and summarizes the existing Phase 10.2 outputs.
