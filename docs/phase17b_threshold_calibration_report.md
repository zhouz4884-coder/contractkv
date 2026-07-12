# Phase 17B: Frozen Threshold Calibration

## Corrected Protocol

The initial calibration protocol accidentally included vLLM's terminal EOS in the answer sequence and appended EOS a second time to the teacher-forced candidate prompt. The verifier therefore inspected the token after the real stop position. This was a code/protocol defect, not evidence against verification-driven promotion.

The repaired protocol uses `split_terminal_stop_token`: teacher-force answer tokens followed by the returned terminal token exactly once. The fresh Qwen3-8B rerun produced 734 candidate rows: 707 completed verifier evaluations, 25 fail-closed `VerificationIncomplete` rows, and 2 missing raw attestations.

The v0/v1 outputs generated before this repair are audit-only and excluded from calibration claims.

## Calibration-Only Selection

Thresholds were selected only on the 357 calibration candidates under these constraints: zero certified unsafe candidates, safe coverage at least 50%, and retained prefix gain at least 50%. The feasible optimum keeps the intrinsic exact-token/top-1/stop gates and adds no margin cutoff:

```json
{"tau_raw": -1000000000.0, "tau_abs": -1000000000.0, "tau_drop": 1000000000.0}
```

| Split | Safe certified | Unsafe certified | Safe coverage | Retained prefix gain |
| --- | ---: | ---: | ---: | ---: |
| Calibration (340 safe, 17 unsafe) | 246 | 0 | 72.35% | 67.52% |
| Held-out (360 safe, 17 unsafe) | 241 | 2 | 66.94% | 63.05% |

The calibration zero-event Wilson 95% upper bound is 18.43%, so this sample cannot establish a 3% unsafe-promotion probability bound. Two held-out false-safe cases remain: `LongBench/qasper/58` (quality drop 0.031358) and `LongBench/narrativeqa/165` (0.050420). They are reported, not tuned away.

See [candidate margins](../results/hard_systems/phase17_calibration_candidate_margins_v2.csv), [frozen thresholds](../results/hard_systems/phase17_frozen_thresholds_v0.json), and [summary](../results/hard_systems/phase17_threshold_calibration_summary_v0.csv).

## Boundary

The frozen threshold is a calibration result, not a production safety guarantee. The remaining held-out misses motivate a richer semantic or task-quality verifier rather than post-hoc threshold adjustment.
