# Phase 21 Generalization Closeout

## Final Decision

Phase 21 is complete and all further model experiments stop. The evidence supports **bounded cross-model generalization**, not a universal session-level certificate.

| Model | Mechanism | Safety policy | Main result |
|---|---|---|---|
| Qwen3-8B | Pass | Pass | 59.13% less new-prefill work; 41.66% net mean TTFT reduction at concurrency 2 |
| Llama-3.1-8B-Instruct | Pass | Fail under old scope | 30.66% less new-prefill work, but stale Turn 0 certificate caused three unsafe certified sessions |
| Mistral-7B-Instruct-v0.3 | Pass | Pass prospectively | 39.46% less new-prefill work; 32.32% net mean TTFT reduction; 0 unsafe certified sessions |

## Why Llama Did Not Pass

The failure is not best described as "ContractKV does not work on Llama."

1. **The physical/cache mechanism worked.** It reduced prefill work, retained 99.924% of certified stable-prefix tokens, and reused zero dynamic-suffix tokens.
2. **The old certificate logic was wrong.** A Turn 0 verifier result was treated as a guarantee for future turns whose observations had changed.
3. **Fresh evidence isolates the cause.** Of 11 reproducible problem rows, fresh strict verification rejected or could not certify 10; the remaining row did not reproduce its quality drop. No freshly accepted row remained quality-bad.
4. **Model sensitivity is a boundary condition, not the identified root cause.** Llama was more sensitive to dynamic layout changes, so the stale-scope error became visible. Current data do not support blaming RoPE, tokenizer, or architecture itself.

The corrected rule is: a certificate is valid only for its frozen model, task family, dependency layout, and observation state. Any relevant change triggers recertification; inability to certify falls back to raw order.

## Engineering Findings

Three compatibility bugs were fixed without weakening the scientific gates:

- repeated ephemeral-hook installation left stale scheduler call sites;
- Mistral's empty chat-template generation suffix was incorrectly treated as protocol divergence;
- same-decoded-string, different-vocabulary-token logprob competitors were incorrectly discarded.

The first two invalidated early smoke attempts. The third depressed development coverage to 24%. All were repaired before the sealed heldout set was opened; final hashes, thresholds, and split commitments were frozen.

## What Generalizes

The defensible architecture is modular:

- dependency-constrained cache-aware layout proposes reuse;
- strict token-path verification attests the current state;
- transactional promotion publishes only verified state;
- fail-closed raw order preserves behavior when no certificate is available.

This substrate produced positive prospective results on Qwen and Mistral. Llama demonstrates why certificate scope must be explicit. Optional RAR and SSPP components can be gated independently, but Phase 21 does not use them to rescue an unsafe layout certificate.

## Paper Position

The strongest cross-model claim is:

> ContractKV's serving mechanism is model-agnostic across the evaluated decoder models, while safe promotion requires scoped behavioral certificates rather than universal session certificates. A prospective Mistral extension passes all frozen safety and performance gates; Llama exposes and validates the fail-closed temporal-scope boundary.

The machine-readable cross-model table is `results/cross_model/phase21_cross_model_summary_v0.csv`. Raw per-request Mistral evidence, frozen split/policy/runtime manifests, protocol audit, quality rows, and load extensions are retained under `results/mistral/`.

## Executed Code Inventory

The following non-test files actually participated in remote execution or final result generation:

- `scripts/run_phase21a.sh`
- `scripts/phase21a_llama_future_turn_recertification_audit.py`
- `scripts/run_phaseM.sh`
- `scripts/run_phaseM_payload_audit.sh`
- `scripts/phaseM_prepare_mistral_split.py`
- `scripts/phaseM_freeze_manifest.py`
- `scripts/phaseM_protocol_audit.py`
- `scripts/phaseM_logprob_payload_audit.py`
- `scripts/phaseM_freeze_policy.py`
- `scripts/phaseM_future_turn_quality.py`
- `scripts/phaseM_summarize_load_extension.py`
- `scripts/phase21_build_cross_model_summary.py`
- `scripts/phase19b_end_to_end_live.py`
- `scripts/phase20a_official_quality.py`
- `scripts/phase16r_verifier_live.py`
- `scripts/install_vllm_v1_ephemeral_shadow_hook.py`
- `scripts/install_vllm_v1_prefix_metrics_probe.py`
- `scripts/run_vllm_server.sh`
- `scripts/stop_vllm_server.sh`
