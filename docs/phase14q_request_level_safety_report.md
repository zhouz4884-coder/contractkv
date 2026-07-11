# Phase 14Q-0 Request-Level Safety Audit

## Result

The request-level recalibration fails closed. Existing paired fresh Qwen3-8B task-sanity labels contain 734 non-raw candidate comparisons across 539 source samples. No calibration threshold can satisfy the 3% Wilson false-safe bound while retaining any nonzero request-level coverage.

| Held-out metric | Result | Required |
| --- | ---: | ---: |
| Selected requests | 0/281 | nonzero |
| Selected false-safe Wilson95 | 1.0 for empty selection | <=0.03 |
| Safe opportunity coverage | 0% | >=60% |
| Unsafe default choices caught | 15/15 | >=80% |
| Retained safe prefix gain | 0% | >=60% |

The audit applies Pareto pruning over predicted new-prefill work, disruption, and predicted risk, then selects one eligible candidate per request. It does not relax the threshold after seeing held-out labels. The correct deployment decision is therefore raw fallback or a stateful behavioral mechanism, not a new static feature sweep.

## Artifacts

- `scripts/phase14q_request_safety_audit.py`
- `results/end_to_end/phase14q_request_safety_audit_v0.csv`
- `results/end_to_end/phase14q_request_safety_summary_v0.csv`
