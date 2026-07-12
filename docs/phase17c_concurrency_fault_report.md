# Phase 17C: Concurrent Promotion and Fault Correctness

The real vLLM Qwen3-4B fault probe completed all 10 scenarios in [phase17_concurrency_fault_v0.csv](../results/hard_systems/phase17_concurrency_fault_v0.csv).

* Two same-prefix passing transactions shared one physical registration: the first added 335 entries and the joiner added zero.
* A same-prefix fail transaction aborted with no certificate while its passing peer committed 414 entries.
* Distinct stable prefixes committed independently.
* Cancel-before, cancel-during, missing-report, and frontend-disconnect cases all aborted fail-closed with zero cache-entry delta and no certificate.
* Each transaction emitted exactly one duplicate-finalization guard event; finalization is idempotent after terminal state.

The hook records pre/post native cleanup free-block counters and physical reference counts. This is an invariant-level stale-pointer signal, not a memory-sanitizer proof.

## Boundary

The test demonstrates source-level transaction isolation and fail-closed cleanup on the exercised paths. It is not a proof over arbitrary vLLM cancellation interleavings.
