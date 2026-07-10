# Phase 14C Full-Pool QC Input Manifest

## Purpose

Phase 14C needs to move beyond the earlier 100-sample QC calibration. This
artifact builds the full-pool calibration and held-out-quality input layer from
the Phase 14D workload pool.

This is not the final QC-CAPOSC gate. It creates:

```text
1. structural features for every calibration/held-out-quality sample
2. raw-order vs ContractKV-CAPOSC fresh-scoring jobs
3. a summary of structural risk signals before labels are available
```

Fresh Qwen3-8B paired outputs are still required before reporting false-safe
rate, false-conservative rate, and safe optimization coverage.

## Inputs

Full pool on the 8T server:

```text
/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv/results/workload/phase14d_full_pool_v0.jsonl
```

Only these disjoint Phase 14D partitions are used:

```text
calibration
held_out_quality
```

The `live_serving` partition is not used for QC feature construction or
quality-label calibration.

## Outputs

```text
results/end_to_end/phase14c_full_pool_qc_features_v0.csv
results/end_to_end/phase14c_full_pool_quality_jobs_v0.jsonl
results/end_to_end/phase14c_full_pool_qc_feature_summary_v0.csv
```

The outputs do not embed the original source prompt text. The job manifest uses
sample keys that can be resolved back to the full JSONL on the 8T disk.

## Scale

```text
features: 537
fresh quality jobs: 1074
policies: raw-order, contractkv-caposc
```

Partition scale:

```text
calibration: 283 samples, 566 jobs
held_out_quality: 254 samples, 508 jobs
```

## Structural Signals

The feature extractor records task-name-free structural signals:

```text
hard_edge_valid
adjacency_preservation
relative_order_edit_distance
ordered_discourse_signal
low_adjacency_signal
segment_type_signature
expected_prefix_gain
estimated_new_prefill_tokens
```

`low_adjacency_signal` is intentionally kept as a feature only. It does not
force fallback by itself, because doing so would over-lock many reorder-safe
samples before labels exist.

The conservative prelabel fallback currently only marks:

```text
dependency-edge violations
ordered discourse moved across a layout edit
```

## Observed Prelabel Summary

Key rows from the full-pool summary:

```text
Qasper calibration: fallback 1.00, mean prefix gain 3610.98 tokens
Qasper held-out: fallback 0.95, mean prefix gain 3429.95 tokens
HotpotQA calibration: fallback 0.00, mean prefix gain 9296.38 tokens
NarrativeQA calibration: fallback 0.00, mean prefix gain 20103.90 tokens
RULER calibration: fallback 0.00, mean prefix gain 715.00 tokens
RepoBench calibration: fallback 0.00, mean prefix gain 1.00 token
```

This is a useful pre-label shape: the known ordered-discourse risk cluster is
identified, while the large-prefix-gain QA/RULER subsets remain available for
fresh-label calibration instead of being prematurely disabled.

## Integrity

```text
phase14c_full_pool_qc_features_v0.csv
sha256: acbb7eab4a1ea2df521426b7d48476f9fcc9e96449b759347a1edb76fa2884e8

phase14c_full_pool_quality_jobs_v0.jsonl
sha256: dc09b8a92716e210ceca86fc5dabc883851c03d434aaff5d64be0bc15f9747d5

phase14c_full_pool_qc_feature_summary_v0.csv
sha256: 6fd6a42eeb4b8174a1658d5bc1664193046249a9ba45457c1ffd80b425a74743
```

## Claim Boundary

This step proves that Phase 14C now has a full-pool, disjoint, task-name-free
calibration input. It does not prove the paper gate:

```text
false-safe rate <= 2%
safe optimization coverage >= 50%
no significant quality drop vs raw
```

Those require running the `1074` fresh-quality jobs and training/evaluating the
QC gate against real paired Qwen3-8B outcomes.
