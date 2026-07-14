# Phase 25: Controlled DeepSeek-V2-Lite Pair

## Status

Phase 25 is complete. The experiment used a prospectively frozen, same-architecture pair:

- DeepSeek-V2-Lite-Chat (general chat)
- DeepSeek-Coder-V2-Lite-Instruct (code specialized)

Both are `DeepseekV2ForCausalLM` models with MLA (`kv_lora_rank=512`) and MoE. All live cells used vLLM 0.10.2 V1, Triton MLA, BF16, TP=2 on two RTX 3090 GPUs, prefix caching enabled, concurrency 2, 8,192 maximum context, and three fresh raw/ContractKV process pairs.

The engineering compatibility gate passed for both models. The preregistered broad-performance gate did not pass for either model.

## Frozen protocol and scale

The protocol was frozen before qualification and sealed replay. A tokenizer-level budget audit selected a 1,150-word stable-context cap, for which all 75 development plus sealed session identities fit within 8,064 input tokens after the chat template. Development and held-out IDs have zero overlap.

- Preflight: 10 sessions/model, two from each of five families.
- Qualification: 25 development sessions/model, L0-L3, five sessions/family.
- Sealed held-out: 50 sessions/model, ten sessions/family, ten turns/session.
- Fresh replay: raw and ContractKV, three process pairs/model.
- Formal held-out total: 6,000 request rows and 5,400 future-turn requests across the pair.
- Diagnostic: 75 development-only level probes/model. The sealed policy was not retuned.

The formal experiment ran from source commit `f72c6ab`. The input and protocol hashes are recorded in `protocol_commitment_v0.json`.

## Compatibility and safety

| Model | Future preflight requests | Fault cases | Committed / aborted | Mean / max physical blocks | Dynamic suffix reuse | Result |
|---|---:|---:|---:|---:|---:|---|
| Chat | 90/90 | 18 | 4 / 14 | 115.67 / 143 | 0 | pass |
| Coder | 90/90 | 18 | 7 / 11 | 135.40 / 272 | 0 | pass |

Every explicit fault aborted with zero cache publication. Every commit was verified and certified. Length-stopped canaries failed closed. Physical block telemetry was read from the real vLLM V1 block path. MLA bytes/block and GiB savings are intentionally not inferred from a GQA formula.

## Sealed global results

| Model | Completion | Certificate coverage | New-prefill reduction | Mean TTFT raw -> ContractKV | Net mean TTFT | p95 TTFT | SLO goodput | Policy quality violations |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Chat | 100% | 6% | 1.83% | 360.27 -> 352.37 ms | 2.18% | 1.39% | +1.69% | 0 |
| Coder | 100% | 20% | 12.17% | 362.46 -> 335.34 ms | 7.48% | -0.17% | +2.96% | 0 |

All fallback sessions are included in these global rows. Output differences observed in raw-fallback pairs are tracked separately and are not attributed to the layout policy. Scope-invalid admissions and dynamic-suffix reuse are both zero.

Neither model met the frozen global gates of 50% certificate coverage, 30% new-prefill reduction, and 25% net mean TTFT reduction. Therefore this experiment does not establish broad MLA+MoE performance generalization.

## Family result and specialization

Only RULER qualified prospectively:

| Model | Frozen RULER level | Held-out coverage | New-prefill reduction | Net mean TTFT | p95 TTFT | SLO goodput |
|---|---:|---:|---:|---:|---:|---:|
| Chat | L2 | 30% | 14.45% | 12.44% | -0.46% | +9.05% |
| Coder | L3 | 100% | 96.09% | 50.54% | 38.36% | +53.80% |

Coder specialization substantially improved RULER token-path robustness and enabled a strong real serving result. It did not expand RepoBench: both models froze RepoBench at L0 with zero held-out certificate coverage. The paired result therefore supports the narrower conclusion that specialization changes robustness for some workflows, but code capability alone is not sufficient for safe code-layout reordering.

## Why is the global benefit low?

The evidence separates three possible causes.

### 1. Final implementation is not the limiting failure

Three implementation/protocol faults were found before sealed replay: a Qwen-specific positive marker in the legacy fault probe, omitted physical-block fields in the result join, and one over-budget RepoBench prompt at the original 1,200-word cap. They were repaired before qualification/held-out use; the cap was frozen at 1,150 only after auditing all 75 identities. Final formal cells have 100% completion, complete physical telemetry, no HTTP capacity errors, and no unsafe publication.

When ContractKV admits a request, certified physical prefix reuse is 99.947% (Chat) and 99.898% (Coder). This directly contradicts the hypothesis that vLLM's MLA prefix-cache path is failing to consume ContractKV layouts.

### 2. The present certificate is conservative for this model family

The development-only diagnostic kept margin gates effectively disabled, so a FAIL occurs when the teacher-forced candidate does not preserve the complete top-1 answer path or terminal stop token. Results were:

| Model | PASS | Strict path/stop FAIL | Raw length-stop |
|---|---:|---:|---:|
| Chat | 10 | 56 | 9 |
| Coder | 20 | 40 | 15 |

PASS and FAIL are also separated by candidate-margin robustness:

| Model | Decision | Candidate margin q05 mean | Candidate margin q05 median | Degradation q95 mean |
|---|---|---:|---:|---:|
| Chat | PASS | 0.4275 | 0.3687 | 1.1256 |
| Chat | FAIL | -0.1628 | -0.1875 | 1.6579 |
| Coder | PASS | 5.9353 | 7.3812 | 0.3530 |
| Coder | FAIL | 0.4594 | 0.5000 | 1.1314 |

This certificate is a sufficient safety condition, not a necessary semantic-equivalence test. A quality-preserving alternative token can therefore cause safe fallback. The low global benefit is chiefly low admission coverage under this strict certificate, not low reuse after admission.

### 3. Model behavior interacts with the frozen output budget

DeepSeek-Coder stopped by length for four of five RepoBench development sessions; each becomes unavailable at L1-L3, producing 12 of its 15 diagnostic incomplete cells. Chat had one such RepoBench session and two Qasper sessions. Because the 128-token output limit was frozen before held-out, these cases correctly fail closed rather than being rescued by post-hoc budget changes.

The evidence does not identify MLA itself as the cause. MLA affects KV representation and memory accounting, but the observed bottleneck occurs before publication in the exact output-path certificate. A more plausible explanation is an interaction between DeepSeek-V2 generation sensitivity, long-form stopping behavior, and ContractKV's current full-path verifier. Improving this boundary requires a separately preregistered semantic or bounded-divergence certificate, not relabeling the current negative result.

## Claim boundary

Phase 25 supports these claims:

1. ContractKV's V1 hooks, PSTP transaction safety, compact verifier, physical block observer, and real prefix reuse are compatible with a DeepSeek-V2 MLA+MoE pair under TP=2.
2. Coder achieves a strong selective RULER result: 50.54% net mean TTFT reduction and 96.09% new-prefill reduction with no attributable quality violation.
3. Broad five-family generalization is not established. Both global primary gates and both RepoBench secondary hypotheses fail.
4. The dominant measured boundary is certificate coverage; MLA byte savings remain unreported because MLA-specific block geometry was not validated.

## Evidence files

- `results/cross_model/deepseek_v2_lite_pair/pair_summary_v0.csv`
- `results/cross_model/deepseek_v2_lite_pair/family_summary_v0.csv`
- `results/cross_model/deepseek_v2_lite_pair/pair_gate_v0.json`
- `results/cross_model/deepseek_v2_lite_pair/certificate_failure_summary_v0.csv`
- `results/cross_model/deepseek_v2_lite_pair/certificate_margin_summary_v0.csv`
- Per-model compatibility, qualification, quality, repeat, and diagnostic files under `results/cross_model/deepseek_v2_lite_pair/{chat,coder}/`.

Raw server logs and full request traces remain on the 8 TB experiment disk under `logs/phase25_deepseek_v2_lite_pair/` and `results/cross_model/deepseek_v2_lite_pair/`; they are not copied into Git.
