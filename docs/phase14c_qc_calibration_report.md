# Phase 14C Held-Out QC-CAPOSC Calibration

## Question

Can a task-name-free structural gate protect against real CAPOSC quality drops while retaining enough safe optimization coverage?

## Data and Gate

The calibration uses the 100 paired fresh Qwen3-8B raw-order/CAPOSC outcomes from Phase 13C. A request is unsafe when its paired task-sanity quality drop exceeds 0.03. This produces 10 unsafe requests: seven Qasper, one HotpotQA, and two NarrativeQA.

The gate uses only structural properties computed from the compiled prompt: hard-edge validity, relative-order edit distance, adjacency preservation, and ordered-discourse heading/cue density. It does not use a task name to select a layout. A candidate that moves an ordered-discourse component is assigned a conservative upper risk of 0.05 and falls back to raw order.

Three views are reported:

```text
calibration/overall: all 100 paired outcomes
held-out trace: sample ids 15-19 from every family
held-out task: Qasper, never selected by a task-name condition
```

## Results

| split | requests | unsafe | fallback | false-safe | safe optimization coverage | unsafe caught |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| overall | 100 | 10 | 20.0% | 3.75% | 85.56% | 70.0% |
| held-out trace | 25 | 4 | 20.0% | 5.00% | 90.48% | 75.0% |
| held-out Qasper task | 20 | 7 | 100.0% | 0.00% | 0.00% | 100.0% |

The generic ordered-discourse signal transfers cleanly to the held-out Qasper task: every held-out Qasper candidate falls back, so the fallback can be made prompt-identical to raw order. However, this first gate **does not pass** the paper threshold of false-safe <= 2% on the held-out trace split. It misses one HotpotQA and two NarrativeQA cases whose compiled layouts have no heading/discourse cue.

## Decision

Do not use this gate as the final QC-CAPOSC policy and do not claim a completed general risk controller. It is useful evidence that hard POSC edges alone are insufficient and that task-name-free ordered-discourse features have real transfer value, but its residual risk is too high.

The correct next step is full-pool fresh calibration, not threshold tuning on these 100 cases. The server holds complete LongBench JSONL pools (200 examples each for HotpotQA/Qasper/NarrativeQA) and complete RepoBench cache files. Phase 14D preparation will create a fixed-seed, stratified large workload and reserve disjoint calibration, held-out quality, and serving-replay partitions. Only a recalibrated gate that meets the held-out 2% false-safe bound can enter the main live-serving comparison.

## Artifacts

```text
scripts/phase14c_qc_calibration.py
results/end_to_end/phase14c_qc_calibration_raw_v0.csv
results/end_to_end/phase14c_qc_calibration_summary_v0.csv
```
