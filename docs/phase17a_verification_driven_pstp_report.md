# Phase 17A: Verification-Driven PSTP Integration

## Objective

Connect a compact, real EngineCore `VerifyReport` to prefix-selective transactional promotion (PSTP). A request may register stable prefix blocks only after verification passes; every other terminal state aborts with no promotion.

## Implementation

`scripts/install_vllm_v1_phase17_hook.py` installs three guarded scheduler hooks in vLLM 0.10.2:

1. Before `_free_request`, it converts `prompt_logprobs_dict[request_id]` into a compact `VerifyReport`.
2. The finalizer maps `PENDING` to `INCOMPLETE`, commits only `PASS` reports with a non-negative reserve and block-aligned prefix, then emits a certificate.
3. Immediately after native cleanup, it records post-cleanup block-pool state.

The runtime registry is an explicit `PSTPPlan` plus mutable `PSTPRuntime`; it does not infer permission from request-ID spelling. `cmpl-...-0` normalization exists solely to map the OpenAI completion adapter's generated ID back to the registered transaction.

## Live Result

The corrected Qwen3-4B EngineCore integration probe contains 16 cases in [phase17_integrated_live_v0.csv](../results/hard_systems/phase17_integrated_live_v0.csv):

| Case | Result |
| --- | --- |
| Safe candidates | 7 `PASS -> COMMITTED`, 5 `INCOMPLETE -> ABORTED` |
| Conflicting candidates | 3 `FAIL -> ABORTED`, 1 `INCOMPLETE -> ABORTED` |
| Gates passed | 16 / 16 |

Committed prefixes were block aligned (361--440 blocks). Certificates were emitted only after commit; aborts had zero cache-entry delta and no certificate. Five safe marker cases failed closed because the compact probe did not expose sufficient prompt-logprob evidence, which is the intended behavior rather than a silent promotion.

## Boundary

This establishes in-engine verification-driven promotion for compact marker requests. It does not establish task-bearing semantic equivalence or an end-to-end speedup.
