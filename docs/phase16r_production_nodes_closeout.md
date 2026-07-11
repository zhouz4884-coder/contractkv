# Phase 16R Production-Node Closeout

## Status

Phase 16R is complete at the independent-node contract and live-prototype level:

- PSTP actuator interface: complete and live block-registration gates passed.
- In-situ verifier decision interface: complete and fail-closed live gates passed.
- Burst-aware quiescence admission interface: complete and live scheduler gates passed.

The three nodes remain deliberately disconnected. Phase 17 is the first phase
allowed to feed a live `VerifyReport.decision` into a `PSTPSpec`.

## What Changed

The decisive engineering correction was removing semantic state from request IDs.
PSTP now uses an explicit immutable transaction object; verifier evidence is based
on backend-native token IDs and logprobs; and shadow admission is based on unified
foreground activity plus hysteresis/backoff. The vLLM patch migration also removes
the legacy `_contractkv_shadow_finalize` call before installing the new finalizer.

## Main Evidence

1. PSTP published only aligned stable blocks, observed zero transaction-specific
   dynamic reuse, and gave zero cache-entry delta for all three abort states.
2. The verifier passed 12 safe cases with positive reserve and failed closed on
   four inconsistent-stop cases. Historical false-safe cases are honestly
   classified as low-margin candidates, not declared solved by threshold tuning.
3. The gate completed all foreground and shadow work, enforced a 32-token cap,
   never co-scheduled foreground and shadow tokens, and exposed collision backoff.

## Actual Result-Producing Code

These non-test files were executed directly or imported by an executed runner:

- `scripts/contractkv_pstp.py`
- `scripts/contractkv_verifier.py`
- `scripts/contractkv_quiescence.py`
- `scripts/install_vllm_v1_ephemeral_shadow_hook.py`
- `scripts/phase16r_pstp_live.py`
- `scripts/phase16r_verifier_live.py`
- `scripts/phase16r_quiescence_live.py`
- `scripts/summarize_phase16r_results.py`
- `scripts/run_phase16r_live.sh`
- `scripts/run_vllm_server.sh`
- `scripts/phase16e_live_transactional_slc.py` (stream request/message helpers)
- `scripts/summarize_vllm_prefix_metrics.py` (prefix-event aggregation)
- `scripts/phase12_prefix_cache_ab.py` (percentile helper)

## Remaining Boundary

“Production-ready” here means the three interfaces and their fail-closed behavior
are frozen and exercised in the real vLLM path. It does not mean an integrated
production deployment. Phase 17 still needs end-to-end decision wiring, concurrent
transaction isolation, calibrated verifier thresholds, and failure-injection tests.
