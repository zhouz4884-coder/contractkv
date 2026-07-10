# Phase 14R Repair Before Scale Report

## Purpose

Phase 14R fixes implementation issues found before running the formal Phase
14D large-scale live serving evaluation.  The goal is not to claim new live
serving speedups yet.  The goal is to make the Phase 14 inputs auditable before
spending GPU time on large runs.

## A. Trace and Opportunity Census Repair

Fixes:

- Code-agent dependency graph now treats repository context as an ordered
  supernode that depends on `SYS_PROMPT`, not on volatile `TOOL_OBS`.
- Query depends on both repository context and tool observation.
- Opportunity gain now uses policy-state segment-prefix ledgers:
  `raw_prefix_reuse_tokens`, `selected_caposc_lcp_tokens`,
  `best_legal_lcp_tokens`, and `caposc_regret_tokens`.
- The old static segment-value gain is no longer used as the main opportunity
  metric.

Result file:

- `results/workload/phase14a_opportunity_census_summary_v1.csv`

Key result:

| workload family | opportunity coverage | safe coverage | median reusable-prefix gain |
| --- | ---: | ---: | ---: |
| code_agent | 0.800 | 0.800 | 1081 |
| rag_agent | 0.800 | 0.560 | 14882 |
| structured_document_qa | 0.800 | 0.000 | 5332 |
| tool_function_agent | 0.800 | 0.800 | 380 |
| mixed_long_history_agent | 0.800 | 0.800 | 400 |

Interpretation:

The previous code-agent 0% opportunity was an implementation artifact.  After
repair, all five workload families show nonzero opportunity, and four of five
families show safe opportunity under the current structural guard.  Structured
document QA remains high-risk/fallback-heavy, which is exactly the kind of
case QC-CAPOSC must learn to handle rather than blindly canonicalize.

## B. Full-Pool and QC-CAPOSC v2 Input Repair

Fixes:

- Full-pool builder no longer uses first-N slicing for LongBench/RepoBench.
- It uses deterministic seeded stratified sampling by context length and source
  group signals.
- Metadata now includes `source_group_id` for partitioning/audit.
- RepoBench case construction was repaired in the serving/quality builder too:
  stable code context can move before volatile tool observations while its
  internal order is preserved.
- Phase 14C job manifest now includes four policies:
  `raw-order`, `canonical-all`, `static-posc`, `contractkv-caposc`.
- The runner now produces candidate labels for every non-raw policy, not only
  for `contractkv-caposc`.
- OpenAI-compatible calls now send deterministic generation controls:
  `temperature=0`, `top_p=1`, `seed=14014`.

Server-resident full pool:

- `/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv/results/workload/phase14d_full_pool_v1.jsonl`
- SHA256: `272c88e8068735b09a0a852d41e1a32b26c773deab6181d427961d6fcd79030c`
- This file remains on the 8T disk and is not tracked in Git.

Tracked lightweight outputs:

- `results/workload/phase14d_full_pool_summary_v1.csv`
- `results/end_to_end/phase14r_qc_features_v2.csv`
- `results/end_to_end/phase14r_qc_feature_summary_v2.csv`
- `results/end_to_end/phase14r_qc_candidate_features_v2.csv`
- `results/end_to_end/phase14r_quality_jobs_v2.jsonl`

Full-pool v1 partition:

| partition | samples |
| --- | ---: |
| calibration | 252 |
| held_out_quality | 289 |
| live_serving | 759 |

QC input scale:

| artifact | rows |
| --- | ---: |
| structural sample features | 541 |
| candidate features | 2705 |
| fresh quality jobs | 2164 |

RepoBench repair check:

| policy/candidate | mean expected prefix gain |
| --- | ---: |
| raw-order | 1.0 |
| POSC | 3399.8 |
| cache-aware POSC | 3399.8 |

Interpretation:

The code-agent serving/quality path is no longer artificially locked.  The
Phase 14D input pool is now suitable for large-scale live serving replay, but
the 2164 fresh quality jobs still need to be run before QC-CAPOSC-v2 can be
claimed as calibrated on the repaired pool.

## C. QC-v2 Calibration Diagnostic

Diagnostic input:

- `results/end_to_end/phase14c_full_pool_quality_labels_v1.csv`
- `results/end_to_end/phase14c_full_pool_qc_features_v0.csv`

Outputs:

- `results/end_to_end/phase14r_qc_v2_scores.csv`
- `results/end_to_end/phase14r_qc_v2_summary.csv`
- `results/end_to_end/phase14r_qc_v2_model.json`

Held-out diagnostic result:

| split | requests | unsafe | fallback rate | false-safe rate | Wilson 95 upper | safe coverage | unsafe caught |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| held_out_quality | 254 | 5 | 0.106 | 0.0176 | 0.0444 | 0.896 | 0.200 |

Interpretation:

The point estimate for held-out false-safe is below 2%, but the Wilson upper
bound is above 2% and unsafe-caught rate is only 20%.  Therefore this diagnostic
must not be reported as the final QC-CAPOSC-v2 safety gate.  It is useful
evidence that the fixed prelabel gate was insufficient and that the repaired
2164-job candidate-level fresh scoring pass is required.

## D. Prefix-Cache Isolation Plan

Fix:

- Added a randomized fresh-server/fresh-cache replication plan for Phase 14B
  validation.

Output:

- `results/prefix_cache/phase14r_prefix_isolation_plan_v1.csv`

Plan:

- policies: `raw-order`, `static-posc`, `cache-aware-posc`
- repeats: 5
- every policy run requires a fresh vLLM process and fresh prefix cache
- run order is randomized per replicate

Interpretation:

The previous Phase 14B prefix-cache result remains useful but should be
revalidated using this isolated plan before being used as a main paper number.

## Status

Phase 14R completes the implementation repair and input regeneration step.
Phase 14D should start only after running the repaired fresh quality jobs, or
should explicitly label QC-CAPOSC-v2 as pending calibration.

Recommended next command on the server:

```bash
cd /media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv
/home/user/miniconda3/envs/contractkv-cu128/bin/python scripts/phase14c_run_full_pool_quality_jobs.py \
  --full-pool results/workload/phase14d_full_pool_v1.jsonl \
  --jobs results/end_to_end/phase14r_quality_jobs_v2.jsonl \
  --features results/end_to_end/phase14r_qc_features_v2.csv \
  --base-url http://localhost:8001/v1 \
  --model qwen3-8b \
  --raw-output results/end_to_end/phase14r_quality_raw_v2.jsonl \
  --labels-output results/end_to_end/phase14r_quality_labels_v2.csv \
  --summary-output results/end_to_end/phase14r_qc_calibration_summary_v2.csv \
  --flush-every 20
```
