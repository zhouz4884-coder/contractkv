# Phase 26 Closeout

## What Was Completed

Phase 26 completed the full audit-to-held-out chain:

1. Token-regret and free-generation audit for all DeepSeek Chat/Coder development candidates.
2. Development-derived output budgets and strict failure taxonomy.
3. Reference-free exact and typed contract library with fail-closed UNKNOWN handling.
4. Safety and benefit transaction fault matrix.
5. A real vLLM TP=2, three-repeat, four-policy sealed DeepSeek-Coder evaluation.
6. A correction experiment that invalidated the v0 cumulative-cost estimator and measured the fused v1 replacement.

Phase 26A found that 78.57% of complete Chat strict failures and 82.05% of complete Coder strict failures were task-safe offline. It also found 12 Chat and 7 Coder genuinely unsafe divergences. Exact-path certification is therefore conservative, but strict failure is not synonymous with semantic safety.

## Final Scientific Result

The strongest safe broad policy is exact-only: zero policy-attributable quality violations, 42% coverage, 29.05% less new-prefill work, and 20.45% lower net mean TTFT. Typed certification raises prefill reduction to 32.67%, but the current QA contract admits eight unsafe Qasper future turns. The production benefit/deadline policy cannot remove this semantic defect and finishes at 46% coverage, 28.91% less new-prefill, and 18.78% lower net mean TTFT.

Accordingly, Phase 26 is complete as a boundary result, not as a successful broad DeepSeek paper gate. The defensible statement is:

> ContractKV's physical prefix lifecycle generalizes to DeepSeek-V2 MLA+MoE, and exact certification preserves quality while reducing real serving work. Broad typed behavioral certification remains limited by future-turn safety for open-ended QA.

It is not defensible to claim that DeepSeek broad-scope generalization passed, or that lexical F1 proves semantic equivalence.

## Root Cause Classification

| Observation | Classification | Evidence |
| --- | --- | --- |
| v0 net TTFT collapse | Code/estimator defect | Cumulative attempts were omitted; fused v1 reduced unhidden r1 cost from 269.32 s to 0.54 s. |
| Exact-only safe but under target | Method conservatism | Zero quality violations, but 42% coverage and 29.05% prefill reduction. |
| Typed Qasper violations | Contract-design defect | Eight violations, all from two typed Qasper sessions; exact-only has zero. |
| Strong RULER and physical reuse | Architecture path works | 100% coverage, 84.84% prefill reduction, 47.98% TTFT reduction, zero suffix reuse. |
| Broad DeepSeek gate fails | Model/workflow plus certificate boundary | DeepSeek generation is path-sensitive on open QA; current Turn-0 typed scope cannot safely certify future turns. |

The evidence therefore rejects both extreme explanations. It is not a broken MLA implementation, and it is not merely an overly strict top-1 check that can be safely relaxed. ContractKV generalizes physically; its present behavioral certificate does not generalize broadly enough on DeepSeek.

## Artifact Map

- `results/cross_model/deepseek_phase26_recoverability/token_regret_summary_v0.csv`
- `results/cross_model/deepseek_phase26_recoverability/recoverability_class_summary_v0.csv`
- `results/cross_model/deepseek_phase26_recoverability/runtime_estimator_repair_v0_v1.csv`
- `results/cross_model/deepseek_phase26_recoverability/heldout_v1_scope_aggregate.csv`
- `results/cross_model/deepseek_phase26_recoverability/heldout_v1_scope_per_repeat.csv`
- `results/cross_model/deepseek_phase26_recoverability/heldout_v1_quality_pairs.csv`
- `results/cross_model/deepseek_phase26_recoverability/phase26d_fused_heldout_gate_v1.json`
- `results/manifests/phase26_hierarchical_behavioral_certification.yaml`

Raw vLLM prefix/block telemetry remains on the 8 TB server. The repository contains the compact joined request records and summaries needed to reproduce the reported tables.
