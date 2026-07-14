# Phase 24: Why and When ContractKV Works

## 1. Purpose and evidence boundary

This phase consolidates existing measurements rather than introducing a new model or mechanism. It answers four submission-facing questions: which model/task scopes admit safe compiled layouts, why the layout ladder is necessary, how expensive model onboarding is, and which observable failure modes cause fail-closed fallback.

The qualification map uses fresh live vLLM held-out measurements. The layout ablation uses the Phase 22 Llama development cells and sealed held-out repeats. Failure-reason and margin tables are diagnostics and are kept separate from the final runtime canary population. Quality is task-sanity scoring on the frozen ContractKV suite, not full official benchmark scoring.

For Qwen and Mistral, `L3*` means the full compiled candidate tested behind a per-session token-path certificate. These two runs did not separately calibrate L1 and L2, so `L3*` must not be read as a full ladder search. Llama levels are the prospectively frozen L0-L3 ladder.

## 2. Cross-model qualification map

| Model | Family | Safe max | Certificate coverage | New-prefill reduction | Net TTFT reduction |
|---|---|---:|---:|---:|---:|
| Qwen3-8B | RULER | L3* | 100% | 96.62% | 85.95% |
| Qwen3-8B | HotpotQA | L3* | 70% | 71.41% | 54.24% |
| Qwen3-8B | NarrativeQA | L3* | 50% | 49.44% | 32.67% |
| Qwen3-8B | Qasper | L3* | 70% | 67.88% | 54.51% |
| Qwen3-8B | RepoBench | L3* | 50% | 43.37% | 21.13% |
| Mistral-7B-Instruct-v0.3 | RULER | L3* | 100% | 95.95% | 87.60% |
| Mistral-7B-Instruct-v0.3 | HotpotQA | L3* | 70% | 69.42% | 65.48% |
| Mistral-7B-Instruct-v0.3 | NarrativeQA | L3* | 60% | 63.50% | 56.63% |
| Mistral-7B-Instruct-v0.3 | Qasper | L3* | 10% | 10.02% | 8.69% |
| Mistral-7B-Instruct-v0.3 | RepoBench | L3* | 10% | 9.80% | -2.22% |
| Llama-3.1-8B-Instruct | RULER | L3 | 100% | 97.06% | 87.52% |
| Llama-3.1-8B-Instruct | HotpotQA | L2 | 90% | 67.52% | 64.57% |
| Llama-3.1-8B-Instruct | NarrativeQA | L2 | 60% | 38.03% | 36.56% |
| Llama-3.1-8B-Instruct | Qasper | L0 | 0% | 0% | -0.22% |
| Llama-3.1-8B-Instruct | RepoBench | L0 | 0% | 0% | 0.80% |

All 15 model/family cells complete 100% of future requests with zero admitted quality violations. The map supports a conditional generalization claim: ContractKV generalizes across all three model families through prospective qualification and raw fallback, while the profitable compiled scope depends on both model and task.

The family rows reconcile exactly to the frozen global net TTFT reductions: 41.66% for Qwen, 32.32% for Mistral, and 29.41% for Llama. Frozen verifier overhead is allocated to families in proportion to measured family canary cost; no overhead is omitted from the family table.

The strongest common scope is RULER, where all models certify every session and reduce new prefill by 95.95% to 97.06%. Retrieval QA remains broadly profitable but needs session-level selection. Qasper and RepoBench expose the model-dependent boundary: Qwen retains 50% to 70% certificate coverage, Mistral drops to 10%, and Llama's frozen policy selects L0. At 10% coverage, Mistral RepoBench's verifier cost outweighs its sparse reuse benefit, producing a -2.22% net TTFT result. This is evidence for adaptive qualification and a minimum-benefit admission rule, not evidence that one model architecture is intrinsically incompatible with ContractKV.

## 3. Layout aggressiveness ablation

| Strategy | Partition | Completion | Safe coverage | Quality violations | New-prefill reduction |
|---|---|---:|---:|---:|---:|
| Always L3 | development | 100% | 56% | 10 / 225 | 48.98% |
| Family-fixed maximum | development | 100% | 52% | 0 / 225 | 32.90% |
| Certificate-guided descent | development | 100% | 52% | 0 / 225 | 32.90% |
| L0 fallback | development | 100% | 0% | 0 / 225 | 0% |
| Family-fixed maximum | sealed held-out | 100% | 48% | 0 / 450 | 30.41% |
| Certificate-guided descent | sealed held-out | 100% | 50% | 0 / 450 | 30.97% |
| L0 fallback | sealed held-out | 100% | 0% | 0 / 450 | 0% |

Always-L3 maximizes speculative reuse but violates the quality contract on 10 development turns. Family qualification removes those violations, and certificate-guided descent recovers two additional percentage points of held-out safe session coverage over a family-fixed level while preserving zero violations. L0 is safe but gives up all reuse. The ladder therefore implements a measurable safety/performance tradeoff rather than a Llama-specific patch.

## 4. Qualification cost and sample stability

The full Llama onboarding used 25 development sessions across five families and four layout cells. The measured development wall time was 645.44 seconds on two RTX 3090 GPUs, or 0.359 GPU-hours. The frozen manifest is 1,678 bytes. A 100,000-iteration lookup microbenchmark measured 0.125 microseconds mean and 0.200 microseconds p95, which is negligible relative to serving TTFT.

| Family | 1 session | 2 sessions | 3 sessions | 5 sessions | Frozen level |
|---|---:|---:|---:|---:|---:|
| RULER | 100% | 100% | 100% | 100% | L3 |
| HotpotQA | 40% | 70% | 90% | 100% | L2 |
| NarrativeQA | 20% | 40% | 50% | 100% | L2 |
| Qasper | 20% | 40% | 60% | 100% | L0 |
| RepoBench | 100% | 100% | 100% | 100% | L0 |

One development session is already stable for the two easiest decisions: always-promote RULER and always-fallback RepoBench. Three sessions recover 90% agreement for HotpotQA, but NarrativeQA and Qasper need all five sessions for deterministic agreement with the final choice. The conservative onboarding recommendation is therefore five sessions per family; it costs less than 0.36 GPU-hours in this setup.

## 5. Certificate failure reasons

Final held-out runtime behavior is fail-closed. Every admitted future request has zero quality violations and zero scope-invalid admissions. Raw fallback is concentrated where the verifier or output budget is least robust:

- Qwen raw fallbacks per ten sessions: RULER 0, HotpotQA 3, NarrativeQA 5, Qasper 3, RepoBench 5. One RepoBench canary ends by length stop.
- Mistral raw fallbacks: 0, 3, 4, 9, and 9. Qasper and RepoBench each contain four length-stop canaries.
- Llama R3 raw fallbacks: 0, 1, 4, 10, and 10. Qasper has four length stops and RepoBench has five; these L0 families do not require certification.

Historical compact Qwen and Mistral canary rows retained generic `FAIL` but not their exact token-path subreason. The table therefore leaves `top1_path_mismatch` and `target_absent` empty for final-runtime rows and reports `unclassified_verifier_fail`. Exact subreasons are provided only in separate diagnostic scopes:

- The Phase 17 Qwen candidate diagnostic contains 207 top-1 path mismatches and 25 target-absent cases across the five named families. Target absence is concentrated in RepoBench (24) plus Qasper (1).
- The Phase 20B Llama rejected-safe diagnostic contains top-1 path divergence in all ten audited cases; four also have length-stop taxonomy. This is a selected rejection diagnostic, not a prevalence estimate.
- The Phase 21 Mistral protocol smoke diagnostic has clean RULER/HotpotQA/NarrativeQA paths and mismatch in both tested Qasper and RepoBench cases. It contains two cases per family and is not a held-out rate.

The unguarded quality diagnostic independently shows why fail-closed admission matters. A physical candidate causes at least one unsafe session for Qwen HotpotQA, Mistral NarrativeQA, and three of five Mistral RepoBench development sessions. Llama's aggressive L3 candidate produces unsafe development sessions in HotpotQA and Qasper. None of these candidate failures are admitted by the final ContractKV policies.

## 6. Margin correlation

The Phase 17 Qwen candidate table contains 734 examples. Passing candidates have a mean candidate margin q05 of 5.674, versus 1.528 for failed candidates. Candidate margin is positively associated with verification success (Pearson `r=0.482`, Spearman `rho=0.578`), while margin degradation is negatively associated (`r=-0.219`).

As expected prefix gain increases across tertiles, pass rate decreases from 77.55% to 64.34% to 57.96%. The correlation between expected prefix gain and pass is modestly negative (`r=-0.195`). The defensible paper wording is:

> Lower token-path robustness is associated with lower safe layout aggressiveness.

This is correlational. It does not identify RoPE, attention architecture, tokenizer family, or any other model component as the root cause.

## 7. Paper-facing conclusion

ContractKV's safe operating region is determined jointly by task structure, model token-path robustness, and the requested layout aggressiveness. A fixed aggressive layout produces larger nominal reuse but violates quality. A frozen family level plus per-session certificate-guided descent preserves completion and quality while retaining substantial prefill and TTFT benefit in the scopes that support it. When a scope is not qualified, L0 fallback preserves correctness with near-zero performance change.

This supports a stronger and more precise claim than universal unconditional speedup: ContractKV provides cross-model serving gains through prospectively qualified adaptive layouts, with explicit fail-closed behavior outside the certified region.

## 8. Artifacts and reproduction

Primary generated artifacts:

- `results/cross_model/phase24_cross_model_qualification_map_v0.csv`
- `results/cross_model/phase24_layout_aggressiveness_ablation_v0.csv`
- `results/cross_model/phase24_qualification_cost_v0.csv`
- `results/cross_model/phase24_qualification_stability_1_2_3_5_v0.csv`
- `results/cross_model/phase24_certificate_failure_reasons_v0.csv`
- `results/cross_model/phase24_external_failure_evidence_v0.csv`
- `results/cross_model/phase24_margin_correlation_v0.csv`
- `results/cross_model/phase24_margin_correlation_summary_v0.json`
- `results/cross_model/phase24_why_when_summary_v0.json`

The analysis is generated by `scripts/phase24_why_when_analysis.py`. Llama repeat-1 canary details and the Mistral protocol audit were read from the preserved 8-TB server result tree; their hashes are frozen in the summary JSON, and the minimal aggregate rows required for offline regeneration are frozen in `phase24_external_failure_evidence_v0.csv`. No new model generation was required.
