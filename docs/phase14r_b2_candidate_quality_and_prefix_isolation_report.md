# Phase 14R-B2 Candidate Quality and Prefix Isolation Report

## Scope

Phase 14R-B2 repairs the remaining candidate-identity, risk-feature, token-budget, split-audit, and prefix-isolation defects before Phase 14D. The paper-facing rule is unchanged: offline opportunity and task-sanity labels cannot substitute for real vLLM serving evidence, and a closed quality gate cannot be bypassed to obtain a favorable performance number.

## Candidate Identity Repair

The quality pipeline now freezes each layout with:

```text
(sample_key, candidate_id, order_hash, prompt_hash)
```

Jobs execute the topological order stored in the manifest. The runner validates the order and all three hashes before sending a request. Labels and features join on `(sample_key, candidate_id)`; no `_base_key()` or forced `contractkv-caposc` identity remains.

The full candidate manifest contains 539 source samples, 1,273 unique legal layout prompts, and 734 non-raw paired comparisons. There are 344 samples with two unique legal layouts and 195 RepoBench samples with three. Duplicate compiler aliases that produce the same prompt hash are scored once.

## Type-Aware Quality Features

Document and code structure are separated:

- document features use headings, discourse cues, and cross-paragraph references;
- code features use internal code-order changes, component crossings, and tool-to-code dependency violations;
- a code supernode whose internal order is preserved is no longer rejected because its text contains words such as `method` or `results`.

The repaired RepoBench candidates expose a mean expected prefix gain of about 3,441 source tokens instead of being structurally locked out.

## Full-Pool Audit

The deterministic pool contains 1,300 source samples:

| Partition | Samples |
| --- | ---: |
| calibration | 258 |
| held-out quality | 281 |
| live serving | 761 |

The split audit reports zero empty/unknown source groups and zero source groups crossing partitions. RepoBench repository IDs preserve `owner/repo` when available. LongBench stratification uses context and answer-length buckets instead of answer text.

## Token-Accurate Census

Phase 14A was rerun with the Qwen3-8B tokenizer, chat template, `max_model_len=8192`, and a 128-token generation reserve. The maximum raw and CAPOSC prompt was 8,064 tokens; 399 long rows were explicitly truncated.

The old 80% opportunity figure was a five-turn construction effect. The corrected report separates overall-turn, warm-turn, and session-level opportunity over 1/2/3/5/8-turn sessions. Warm-turn and session-level opportunity are 100% for all five workload families once a prior turn exists.

Legal-oracle LCP now enumerates up to 64 legal topological orders. CAPOSC had nonzero legal-oracle regret in 0 of 1,900 tokenized census rows.

## Fresh Quality Matrix

All 1,273 deterministic Qwen3-8B requests completed successfully. The final audit has no missing, unexpected, or failed manifest jobs and produces 734 paired candidate labels.

| Dataset/task | Paired candidates | Unsafe candidates (>3% drop) |
| --- | ---: | ---: |
| RULER niah | 93 | 0 |
| LongBench hotpotqa | 82 | 1 |
| LongBench narrativeqa | 82 | 9 |
| LongBench qasper | 87 | 7 |
| RepoBench python | 390 | 17 |
| Total | 734 | 34 |

These are fresh task-sanity scores, not official benchmark scores. They nevertheless show that topological legality alone does not guarantee output invariance.

## QC Gate Result

The candidate calibrator now maximizes retained safe prefix gain subject to a calibration Wilson95 false-safe upper bound of 3%. Deployment additionally requires held-out safe coverage at least 80% and unsafe-candidate catch rate at least 80%.

The final model is fail-closed:

```text
deployment_gate_open = false
fallback_rate = 100%
safe_optimization_coverage = 0%
unsafe_caught_rate = 100%
```

This is not a successful deployable QC selector. The current generic structural features do not predict the 34 layout-sensitive candidates well enough to satisfy both finite-sample safety and useful coverage. Phase 14D therefore refuses a full run unless an explicit smoke-only override is provided.

## Fresh-Process Prefix Isolation

The prefix-cache mechanism was independently replicated with 15 fresh vLLM processes: three policies times five randomized repetitions. Every cell starts from a fresh process and empty prefix cache, uses a separate scheduler metrics log, and joins observations using the server-issued request ID.

| Policy | Requests | Mean TTFT | p95 TTFT | Mean observed new prefill | Mean TTFT reduction | New-prefill reduction | Direction |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| raw-order | 90 | 144.612 ms | 489.842 ms | 350.778 tokens | baseline | baseline | 5/5 |
| static POSC | 90 | 126.808 ms | 448.196 ms | 274.333 tokens | 12.31% | 21.79% | 5/5 |
| cache-aware POSC | 90 | 119.440 ms | 448.046 ms | 244.889 tokens | 17.41% | 30.19% | 5/5 |

All 270 requests completed, passed marker sanity, and joined scheduler metrics. This is real vLLM evidence that CAPOSC reduces new prefill work and mean TTFT under process/cache isolation. The p95 reduction is 8.53%, below the planned 10% strong threshold, so the claim should emphasize mean TTFT and observed prefill work.

## Phase 14D Decision

A 20-request live smoke validated the Phase 14D runner and exposed/fixed a session-nonce bug in dynamic tool observations. The formal 9,600-request mixed-agent run was not launched because the QC deployment gate is closed.

The next defensible design step is a stateful quality mechanism, such as a shadow first-turn canary or a richer content-aware risk model, followed by a new untouched quality split. It is not defensible to relax the Wilson bound after seeing the held-out failures.

## Artifacts

```text
results/workload/phase14a_opportunity_census_raw_v2.csv
results/workload/phase14a_opportunity_census_summary_v2.csv
results/workload/phase14d_full_pool_audit_v2.csv
results/workload/phase14d_full_pool_summary_v2.csv
results/end_to_end/phase14r_qc_candidate_features_v5.csv
results/end_to_end/phase14r_quality_jobs_v5.jsonl
results/end_to_end/phase14r_quality_labels_v5.csv
results/end_to_end/phase14r_quality_label_summary_v5.csv
results/end_to_end/phase14r_quality_audit_v5.csv
results/end_to_end/phase14r_qc_v2_summary_v5.csv
results/end_to_end/phase14r_qc_v2_model_v5.json
results/prefix_cache/phase14r_prefix_isolation_raw_v1.csv
results/prefix_cache/phase14r_prefix_isolation_summary_v1.csv
```

The large full-pool JSONL, full model outputs, per-cell server logs, and scheduler event logs remain on the 8T server disk.
