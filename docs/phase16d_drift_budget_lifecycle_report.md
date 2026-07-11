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
then evaluated on odd-numbered held-out sessions. The synthetic label is now
named `unrenewed_answer_change_exposure`: it is a renewal-pressure diagnostic,
not a raw-vs-candidate semantic mismatch.

## Result

Calibration split:

| Policy | Coverage | Exposure Wilson95 | Retained prefix gain | Semantic gate |
| --- | ---: | ---: | ---: | --- |
| calibrated full-native drift | 47.0% | 2.00% | 29.65% | not applicable |
| fixed TTL-3 | 78.0% | 39.07% | 48.64% | not applicable |
| token-only | 97.0% | 37.55% | 60.82% | not applicable |

Held-out split:

| Policy | Coverage | Exposure Wilson95 | Retained prefix gain | Semantic gate |
| --- | ---: | ---: | ---: | --- |
| calibrated full-native drift | 53.25% | 2.61% | 33.46% | not applicable |
| conservative full-native drift | 46.0% | 3.01% | 28.96% | not applicable |
| fixed TTL-3 | 78.5% | 36.79% | 49.47% | not applicable |

## Interpretation

The Wilson denominator is now the number of covered turns, rather than all
future turns. More importantly, answer change is no longer presented as layout
mismatch. These numbers only compare lifecycle renewal pressure and retained
prefix opportunity.

The actual raw-vs-candidate divergence is reanalyzed from the real Phase 15D
Qwen3-8B outputs. Among 203 CAPOSC-covered future turns there is one output
contract divergence: 0.493%, with a Wilson 95% upper bound of 2.737%. The 97
renewed/raw turns are excluded from the denominator.

That means synthetic Phase 16D remains a lifecycle diagnostic. The real
conditional divergence estimate is stronger evidence, but it is task-sanity
rather than full official scoring and still does not replace the in-situ margin
verifier from Phase 16C.

## Artifacts

- `scripts/phase16d_drift_budget_lifecycle.py`
- `results/runtime/phase16d_drift_budget_raw_v0.csv`
- `results/runtime/phase16d_drift_budget_summary_v0.csv`
- `results/runtime/phase16d_real_divergence_reanalysis_v0.csv`
