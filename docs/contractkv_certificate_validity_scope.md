# ContractKV Certificate Validity Scope

## Status

This document freezes the validity boundary used by the submission replay.
ContractKV certificates are empirical attestations, not proofs of semantic
equivalence. Every reuse decision is fail-closed and publication remains a
separate transactional operation.

## Identity tuple

Every certificate binds the following tuple:

```text
model_identity
task_family
layout_hash
stable_prefix_hash
scope_mode
observation_identity / observation_epoch
policy_hash
qualification_hash
```

Reuse is rejected if the model, task family, dependency-valid layout, stable
prefix content, or frozen policy differs from the request context.

## Observation scope

`observation` is the narrow mode. The certificate is valid only for the exact
observation content and epoch that was verified. It is intended for one-shot
promotion and diagnostic experiments.

## Qualified-session scope

`qualified_session` permits future observations only when the model, task
family, stable prefix, dependency-valid layout, policy, and independently
frozen qualification hash remain identical. This mode is used by the final
multi-turn Qwen and Mistral replay. Observation changes alone do not admit a
layout: the session-level qualification artifact is part of the identity.

## Failure behavior

Any missing identity or mismatch produces explicit error labels and forces
raw-order execution. An unknown scope mode is invalid. No error path silently
widens a certificate.

The implementation lives in `scripts/contractkv_certificate_scope.py`; the
request-path integration is in `scripts/phase19b_end_to_end_live.py` and the
vLLM-adjacent transaction hook is installed by
`scripts/install_vllm_v1_phase17_hook.py`.

## Claim boundary

The certificate supports a measured operational claim: within a frozen,
empirically qualified identity scope, ContractKV may reuse a verified stable
prefix and transactionally publish it. It does not establish correctness for a
new model, task family, prompt dependency graph, or stable-prefix content.
