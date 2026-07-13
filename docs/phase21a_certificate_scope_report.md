# Phase 21A: Llama Future-Turn Certificate Audit

## Question

Phase 20 showed that the Llama serving mechanism reduced new-prefill work by 30.66% and net mean TTFT by 26.68%, yet three certified sessions later violated the quality budget. Phase 21A tests whether this was a broken token-path verifier or an invalid temporal scope for the original Turn 0 certificate.

## Method

The audit replays the 11 previously identified reproducible future-turn rows. Each changed observation is checked again with the strict token-path verifier, using the frozen policy and no threshold tuning. A row is classified as:

- `STALE_SESSION_CERTIFICATE` when the old session certificate admitted the row but fresh verification rejects or cannot certify it;
- `UNSOUND_FRESH_VERIFIER` only if fresh verification passes while the reproduced quality drop remains above 0.03;
- `NO_REPRODUCED_QUALITY_DROP` when the old violation does not reproduce.

## Result

| Measure | Value |
|---|---:|
| Audited rows | 11 |
| Fresh rejected or incomplete | 10 |
| Fresh pass with quality drop | 0 |
| Quality drop not reproduced | 1 |

The result diagnoses **stale certificate scope**. The strict verifier did not approve any reproduced bad future turn. The old policy treated a Turn 0 attestation as a session-wide guarantee even after dynamic observations changed. That logical implication is invalid.

## Code, Idea, and Model Factors

**Code defects found during this audit.** The ephemeral-hook installer left duplicate grant-cap call sites after repeated installations, causing a transient `NameError`; the cleanup routine now removes every installed copy. This invalidated early audit attempts but does not explain the original Phase 20 result, which had completed successfully before this audit.

**Primary design defect.** The certificate lacked an explicit temporal scope. A current-turn proof was used as if it certified all future turns. Future-turn changes must trigger recertification or fail closed.

**Model factor.** Llama exhibited greater output sensitivity to dynamic layout changes than Qwen in this workload. That affects certificate coverage, but the audit does not establish tokenizer, RoPE, or architecture as the root cause. The causal failure was policy scope: fresh verification correctly rejected the unsafe rows.

## Corrected Contract

The deployable abstraction is a model/task/observation-scoped certificate, not a universal session certificate. When the certificate is invalid or unavailable, ContractKV preserves raw order and native vLLM prefix behavior. Other lifecycle primitives can remain independently gated, but they are not inferred from this audit.

Machine-readable evidence is in `results/cross_model/phase21a_llama_future_turn_audit_v0.csv` and `phase21a_llama_future_turn_summary_v0.json`.
