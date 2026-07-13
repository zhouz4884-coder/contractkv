# Phase 20D: Sealed One-Shot Cross-Model Evaluation

## Frozen setup

The policy was frozen after 25 development sessions and evaluated once on 50 fresh Llama heldout sessions: ten each from RULER, HotpotQA, NarrativeQA, Qasper, and RepoBench. Sample IDs and source groups are disjoint from development and prior Phase 19 sessions.

Four policies were compared: raw order, a physical-cache-aware upper bound, Tier 1 only, and frozen ContractKV two-tier. The valid run processed sessions cohort by cohort; an earlier implementation that certified all sessions before future turns was discarded because it unfairly changed cache residency.

## Main result

| Metric | Raw order | Tier 1 only | ContractKV two-tier |
| --- | ---: | ---: | ---: |
| Completion rate | 100% | 100% | 100% |
| Mean TTFT (ms) | 1,324.930 | 972.318 | 971.437 |
| p95 TTFT (ms) | 2,553.404 | 2,558.693 | 2,534.610 |
| Mean new-prefill tokens | 3,370.560 | 2,337.102 | 2,337.102 |
| Safe coverage | 0% | 44% | 44% |
| Unsafe certified sessions | 0 | 3 | 3 |

ContractKV reduced mean TTFT by 26.68% and new-prefill work by 30.66%, with 99.924% certified-prefix reuse and zero dynamic-suffix reuse. Foreground p95 interference relative to the identical Tier 1 lifecycle was -24.082 ms. Tier 2 was never admitted under the frozen 14.5 s budget.

## Gate and causality audit

The submission gate failed: safe coverage was below 50%, net TTFT reduction was below 30%, and three certified sessions had future-turn quality violations. Among 198 audited future rows from 22 certified sessions, 11 violating rows were reproducible across Tier 1 and two-tier runs, while one row was attributable to cross-process variation or a score boundary.

This isolates a policy assumption failure: Turn 0 attestation does not prove later turns remain safe after dynamic observations change. It is not evidence that Tier 2 corrupted state, because the certificate set was identical and Tier 2 never executed on heldout data.

## Claim boundary

This is a negative but causal cross-model result. It supports work-reduction and mean-TTFT benefits on Llama, but it does not pass the frozen safety/performance gate and therefore cannot support a general cross-model headline claim.
