# Phase 14C Full-Pool QC-CAPOSC Calibration

## Question

Can a task-name-free structural QC gate protect CAPOSC from quality regressions
on a larger disjoint full-pool calibration, while preserving enough safe
optimization coverage for Phase 14D live serving?

## Inputs

Full-pool feature/job manifest:

```text
results/end_to_end/phase14c_full_pool_qc_features_v0.csv
results/end_to_end/phase14c_full_pool_quality_jobs_v0.jsonl
```

Fresh Qwen3-8B quality run:

```text
remote raw outputs:
/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv/results/end_to_end/phase14c_full_pool_quality_raw_v1.jsonl

tracked labels:
results/end_to_end/phase14c_full_pool_quality_labels_v1.csv
results/end_to_end/phase14c_full_pool_qc_calibration_summary_v1.csv
```

The raw output file remains on the 8T server because it contains model output
text. The tracked label CSV contains paired scores, request ids, and QC metrics.

## Important Correction

An initial v0 run reused a Phase 13B helper that embedded the policy name in
the system namespace. That contaminated quality attribution because raw-order
and CAPOSC differed by more than layout. The v1 run fixes this by using a
policy-neutral namespace:

```text
PHASE14C:{dataset}:{task}:{sample_id}
```

The v1 labels are the only labels used for the Phase 14C result below.

## Scale

```text
fresh jobs: 1074 / 1074
paired labels: 537 / 537
calibration pairs: 283
held-out-quality pairs: 254
model: Qwen3-8B
endpoint: http://localhost:8001/v1
```

## Gate

The evaluated structural gate is task-name-free. It uses generic layout and
document-structure features:

```text
dependency-edge validity
ordered-discourse signal
segment type composition
layout edit distance
adjacency preservation
estimated prefix gain
```

The prelabel fallback marks dependency violations and ordered-discourse layout
edits. It does not use task names.

## Results

| split | requests | unsafe | fallback | false-safe | safe optimization coverage | unsafe caught | mean drop |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 537 | 15 | 15.64% | 2.43% | 84.67% | 26.67% | 0.007766 |
| calibration | 283 | 10 | 16.25% | 3.80% | 83.52% | 10.00% | 0.011760 |
| held-out quality | 254 | 5 | 14.96% | 0.93% | 85.94% | 60.00% | 0.003317 |

Held-out task rows:

```text
HotpotQA: false-safe 0.00%, coverage 100.00%
NarrativeQA: false-safe 5.56%, coverage 100.00%
Qasper: false-safe 0.00%, coverage 5.41%
RULER: false-safe 0.00%, coverage 100.00%
RepoBench: false-safe 0.00%, coverage 100.00%
```

## Gate Decision

The Phase 14C held-out gate passes the paper threshold:

```text
held-out false-safe rate = 0.9259% <= 2%
held-out safe optimization coverage = 85.9438% >= 50%
held-out mean quality drop = 0.003317
```

This is strong enough to let QC-CAPOSC enter the Phase 14D live-serving main
comparison.

## Remaining Caveat

The calibration split still has higher residual false-safe rate:

```text
calibration false-safe rate = 3.7975%
```

The misses concentrate in HotpotQA/NarrativeQA layout sensitivity. Therefore
the paper should report both the passing held-out gate and this residual
calibration weakness. Phase 14D should keep `canonical-all` and `CAPOSC without
QC` as ablations so the benefit of QC-CAPOSC is visible rather than assumed.

## Integrity

```text
phase14c_full_pool_quality_raw_v1.jsonl
remote sha256: afe11f86098e092eaecb6a11fdc6ddd269c136ff189778a4c244784dd83ad1e1

phase14c_full_pool_quality_labels_v1.csv
sha256: f70efa6a00da90e3ef63bec83670e24229956d64df0ba196d270f2e6b2e94706

phase14c_full_pool_qc_calibration_summary_v1.csv
sha256: bb830eaf1907984c145319ad33f0c0a6450deed5be4feac05e1ee5d99cded574
```

## Claim Boundary

This is task-sanity scoring, not official LongBench or RepoBench scoring. It is
valid as a QC gate for Phase 14D serving experiments, but the final paper should
still keep official-task-score language separate from this calibration result.
