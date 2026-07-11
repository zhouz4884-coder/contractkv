# Phase 16D Drift-Bounded Certificate Lifecycle

## Goal

Phase 16D separates semantic certificate validity from physical prefix
availability. Cache eviction or preemption is residency pressure; it is not
semantic drift. A certificate therefore has two axes:

```text
semantic_state: VALID / RENEWAL_PENDING / REVOKED
residency_state: HOT / PARTIAL / COLD
```

## Method

The executable prototype builds a synthetic answer-changing multi-turn pool with
Qasper-like, RepoBench-like, RULER-like, and tool-agent-like sessions. It compares:

- fixed TTL 1/3/5
- token-only drift
- token + position drift
- full-native drift
- calibrated full-native drift

The calibrated policy is selected only on even-numbered calibration sessions and
then evaluated on odd-numbered held-out sessions.

## Result

Calibration split:

| Policy | Coverage | Mismatch Wilson95 | Retained prefix gain | Gate |
| --- | ---: | ---: | ---: | --- |
| calibrated full-native drift | 50.0% | 2.89% | 31.75% | pass |
| fixed TTL-3 | 78.0% | 30.77% | 48.64% | fail |
| token-only | 97.0% | 36.47% | 60.82% | fail |

Held-out split:

| Policy | Coverage | Mismatch Wilson95 | Retained prefix gain | Gate |
| --- | ---: | ---: | ---: | --- |
| calibrated full-native drift | 56.5% | 3.90% | 35.67% | fail |
| conservative full-native drift | 46.0% | 1.40% | 28.96% | fail coverage |
| fixed TTL-3 | 78.5% | 28.42% | 49.47% | fail |

## Interpretation

This is the important lesson: the lifecycle design is right, but the current
synthetic drift model is not deployment-ready. Calibration can find a point that
passes on the calibration split, but it does not yet generalize below the 3%
Wilson bound on held-out while keeping coverage above 50%. A more conservative
full-native policy is safe but loses too much coverage.

That means Phase 16D should be treated as a protocol result, not a final
certification result. The next implementation should use real answer-changing
future-turn data and the in-situ margin verifier from Phase 16C.

## Artifacts

- `scripts/phase16d_drift_budget_lifecycle.py`
- `results/runtime/phase16d_drift_budget_raw_v0.csv`
- `results/runtime/phase16d_drift_budget_summary_v0.csv`
