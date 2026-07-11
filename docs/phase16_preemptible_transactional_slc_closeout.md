# Phase 16 Closeout: Preemptible Transactional SLC

## Summary

Phase 16 integrates three design additions into one safety plane:

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

This supports a one-micro-chunk bounded interference design, with 16/32/64 as
safe first candidates and 128 as too large under the current gate.

## B. KV Transaction Plane

The ephemeral namespace model passes the core correctness checks across 1000
cycles:

- block leak count: 0
- stale hash pointers: 0
- cache-table inconsistencies: 0
- promotion p95: 0.237 ms
- rollback p95: 0.146 ms

This is the strongest new mechanism in Phase 16. It directly solves the cache
safety question that Phase 15D exposed: failed canaries must not leave globally
visible prefix-cache state.

## C. Verifier Plane

Phase 16C is a design target rather than a new measured run. It should turn SLC
v2 into an in-situ verifier with raw margin capture, candidate teacher-forced
verification, early abort, and transaction commit/rollback. The existing SLC v2
evidence remains the measured baseline: 66.08% certificate issue rate and
94.12% unsafe rejection, with two held-out false-safe cases.

## D. Certificate Lifecycle

The drift-budget prototype confirms the modeling direction but does not yet
produce a deployment-ready threshold:

- calibration split: calibrated full-native drift passes with 50.0% coverage
  and Wilson95 2.89%
- held-out split: calibrated full-native drift has 56.5% coverage but Wilson95
  3.90%
- conservative full-native drift is safe on held-out, Wilson95 1.40%, but only
  46.0% coverage

This tells us the problem is not the lifecycle idea. The missing piece is real
answer-changing future-turn calibration plus in-situ margin signals.

## Claim Boundary

Supported now:

- scheduler design can bound active interference in an executable model
- ephemeral KV transaction invariants hold in an in-memory correctness model
- drift-budget lifecycle needs calibration/held-out validation and cannot be
  replaced by fixed TTL

Not yet supported:

- vLLM source-level micro-chunk scheduling
- vLLM block-pool transactional promotion
- production in-situ margin verifier
- deployable drift thresholds on real answer-changing workloads

## Artifacts

- `docs/phase16a_microchunk_scheduler_report.md`
- `docs/phase16b_ephemeral_kv_transaction_report.md`
- `docs/phase16c_in_situ_margin_verifier_design.md`
- `docs/phase16d_drift_budget_lifecycle_report.md`
- `results/manifests/phase16_preemptible_transactional_slc.yaml`
