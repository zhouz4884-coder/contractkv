# Phase 15 Closeout

## Summary

Phase 15 closes the main fairness, causality, and quality gaps that remained
after Phase 14. The headline result is now defensible:

ContractKV/CAPOSC produces real vLLM serving gains under fair fresh-process
replay, the finite-capacity claim survives an async-client correction, physical
cache-state feedback adds value beyond static POSC, and Certified CAPOSC
preserves task behavior on a task-bearing live replay with a measured residual
risk boundary.

## A. Fairness And Tail Diagnosis

Phase 15A verifies that policy rows join one-to-one across raw-order, static
POSC, and CAPOSC. All 450 row-wise keys match across policies, including
content signatures, prompt-token counts, and source labels. Warm-turn results
show the real serving effect:

- concurrency 1: CAPOSC warm mean TTFT 79 ms vs raw 1,471 ms
- concurrency 4: CAPOSC warm mean TTFT 666 ms vs raw 4,303 ms

The all-turn tail is partly cold-start dominated, so paper tables should report
both all-turn and warm-turn views.

## B. Async Capacity Recheck

Phase 15B replaces the earlier synchronous-client capacity result. The corrected
async-client result is:

- raw-order stable at 0.9 rps, unstable at 1.0 rps
- CAPOSC stable at 12 rps, unstable at 16 rps
- stable-point ratio: 13.33x
- strict lower bound: greater than 12x

The old 56 rps / 112x value is superseded and should not be used as a final
paper claim.

## C. Cache-State Causality

Phase 15C shows that physical cache-state feedback is useful when logical
layouts conflict with actual vLLM residency:

- Qwen3-8B: physical-residency CAPOSC reduces mean TTFT by 45.45% and p95 TTFT
  by 45.41% versus static POSC.
- Qwen3-4B: the same mechanism reduces mean TTFT from 649 ms to 375 ms.
- native block-hash churn probe: one-round adaptation success 100%, within-one-
  block selection 100%, maximum continuous stale rounds 0.

The boundary remains read-only cache-state observation plus layout selection,
not real KV movement.

## D. Certified Task-Bearing Deployment

SLC v2 certifies 66.08% of candidates, rejects 94.12% of known unsafe
candidates, and retains 64.40% prefix gain among certified candidates. Two
held-out false-safe cases remain, so the guard is strong but not perfect.

The live task-bearing replay has 60 sessions and 205 future pairs:

- certificate issue rate: 68.33%
- future mismatch rate: 0.49%
- Wilson 95% upper bound: 2.71%
- mean quality drop: 0.000608
- warm TTFT reduction: 51.39%
- warm new-prefill reduction: 55.60%
- violated dependency edges: 0

Active-tenant interference is the main remaining systems caveat: shadow canary
work raises active p95 TTFT by about 585 ms in the small Qwen3-8B probe. Canary
or verifier work must therefore be scheduled under slack, isolated, or
rate-limited.

## Paper-Ready Claim Boundary

Supported:

- real vLLM serving TTFT and capacity gains from cache-aware layout
- async-client corrected finite-capacity lower bound
- native prefix-cache state observation as a compiler signal
- task-bearing certified deployment with low observed mismatch

Not yet supported:

- real KV block movement or mutation of vLLM's block manager
- full official benchmark scoring over all tasks
- zero-cost online certification on the active serving GPU

## Artifacts

- `docs/phase15a_fair_replication_report.md`
- `docs/phase15b_shared_capacity_report.md`
- `docs/phase15c_cache_state_adaptation_report.md`
- `docs/phase15d_task_bearing_certification_report.md`
- `results/manifests/phase15_fairness_cache_certification.yaml`
