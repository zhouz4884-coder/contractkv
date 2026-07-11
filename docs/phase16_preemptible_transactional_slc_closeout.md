# Phase 16 Closeout: Preemptible Transactional SLC

## Summary

Phase 16 integrates three design additions into one safety plane and Phase 16E
pushes the scheduler and transaction pieces into real vLLM V1:

- preemptible micro-chunk scheduling decides when shadow verification may run
- ephemeral KV transactions prevent failed verification from polluting cache
- drift-bounded certificates decide when a prior certificate must renew

The resulting system direction is:

> ContractKV executes candidate-layout certification as an idle-only,
> micro-preemptible KV transaction. Candidate blocks remain invisible until
> token-path, margin, and stopping checks pass; only certified stable-prefix
> blocks are atomically promoted. Certificates then live under a measured drift
> budget instead of a fixed TTL.

## A. Scheduler Plane

The scheduler-only model shows that naive ordinary shadow work causes large
active interference, while IDLE_ONLY micro-chunks bound it:

- naive ordinary shadow p95 penalty: 444.8 ms
- IDLE_ONLY-16 p95 penalty: 2.7 ms
- IDLE_ONLY-32 p95 penalty: 4.2 ms
- IDLE_ONLY-64 p95 penalty: 8.2 ms
- IDLE_ONLY-128 p95 penalty: 14.0 ms

These modeled values selected 16 and 32 for source-level validation. The fair
Qwen3-4B Phase 16E run measured +10.96 ms p95 for 16 tokens and +11.91 ms for
32 tokens. Both are much smaller than the prior +585 ms ordinary-shadow result,
but both narrowly fail the 10 ms gate. The model was useful for candidate
selection but underestimated real scheduling/kernel overhead.

## B. KV Transaction Plane

The ephemeral namespace model passes the core correctness checks across 1000
cycles:

- block leak count: 0
- stale hash pointers: 0
- cache-table inconsistencies: 0
- transaction metadata leaks: 0
- promotion p95: 0.219 ms
- rollback p95: 0.137 ms

Phase 16E then validates the mechanism in vLLM: abort leaves the global cache
table unchanged and gives 0.48% reuse, while commit registers 246 real full
blocks in 0.396 ms and gives 99.85% reuse to the next identical request. This is
the strongest new hard-system result in this closeout.

## C. Verifier Plane

Phase 16C now has a minimal same-vLLM-backend prompt-logprob probe: 12/12 marker
cases passed and all 146 answer tokens remained candidate top-1, with minimum
top1 margin 8.56. This is a real backend-alignment smoke, while the existing SLC
v2 evidence remains the broader baseline: 66.08% certificate issue rate and
94.12% unsafe rejection, with two held-out false-safe cases. EOS/stop checks,
real-task thresholds, early abort, and atomic commit-after-verification remain.

## D. Certificate Lifecycle

The drift-budget prototype is now explicitly an exposure diagnostic rather than
a semantic mismatch estimator. It uses covered turns as the Wilson denominator
and never opens a semantic deployment gate.

- synthetic held-out calibrated coverage: 53.25%
- synthetic held-out unrenewed-answer-change exposure Wilson95: 2.61%
- real Phase 15D covered future turns: 203
- real raw-vs-candidate divergences: 1 (0.493%)
- real conditional Wilson95 upper: 2.737%

This repairs the earlier statistical interpretation. The missing piece remains
real answer-changing future-turn calibration plus in-situ margin signals.

## Claim Boundary

Supported now:

- real vLLM IDLE_ONLY micro-chunk scheduling removes most ordinary-shadow
  interference, though it misses the strict p95 gate by about 1 ms
- real vLLM delayed block registration provides abort isolation and commit reuse
- ephemeral transaction invariants, including metadata cleanup, hold across
  1000 randomized in-memory cycles
- drift-budget lifecycle needs calibration/held-out validation and cannot be
  replaced by fixed TTL

Not yet supported:

- zero-cost or sub-10-ms vLLM shadow scheduling
- concurrent/partial-block transactional promotion
- production in-situ verifier with stop checks and real-task thresholds
- deployable drift thresholds on real answer-changing workloads

## Artifacts

- `docs/phase16a_microchunk_scheduler_report.md`
- `docs/phase16b_ephemeral_kv_transaction_report.md`
- `docs/phase16c_in_situ_margin_verifier_design.md`
- `docs/phase16d_drift_budget_lifecycle_report.md`
- `docs/phase16e_vllm_transactional_shadow_report.md`
- `results/manifests/phase16_preemptible_transactional_slc.yaml`
