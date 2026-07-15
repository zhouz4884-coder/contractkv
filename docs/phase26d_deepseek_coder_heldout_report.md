# Phase 26D: DeepSeek-Coder Hierarchical Certification Held-out

## Protocol

DeepSeek-Coder-V2-Lite-Instruct was evaluated with vLLM V1, TP=2, bfloat16, prefix caching enabled, two RTX 3090 GPUs, 50 sealed sessions, five workflow families, ten turns per session, and concurrency two. Each of four policies ran in three fresh server processes:

- raw order;
- exact certificate only;
- exact plus typed certificate without the production deadline;
- exact plus typed plus deadline/benefit policy (`contract`).

Every cell contains 50 canaries and 450 measured future requests. All 12 cells completed, for 5400 successful future requests. The frozen qualification hash is `7250e1216dcb25d8b40186a3c47aeb569fb2d52dc70c1b515d5fe06cbdf6cdfd`; the held-out split hash is `31397988f5dd1f0ba0a8758d39c9f657bf6b9e85f9fc15cc2a447ba6b4445b9a`.

## Global Results

| Policy | Coverage | New-prefill reduction | Net mean TTFT reduction | Net p95 TTFT reduction | Policy quality violations |
| --- | ---: | ---: | ---: | ---: | ---: |
| Raw | 0.00% | 0.00% | 0.00% | 0.00% | 0 |
| Exact | 42.00% | 29.05% | 20.45% | 25.00% | 0 |
| Exact + Typed | 48.00% | 32.67% | 21.25% | 22.81% | 8 |
| Exact + Typed + Benefit | 46.00% | 28.91% | 18.78% | 14.07% | 8 |

The production-style contract reduced mean TTFT from 374.85 ms to 304.39 ms after charging unhidden verification work. Mean verifier time was 1352.05 ms per session, but 6000 ms tool slack hid almost all of it; only 534.03 ms remained across 1350 future requests. At a 1500 ms SLO, net SLO goodput improved by 2.14%.

The v0-to-v1 correction is material. The v0 multi-attempt verifier averaged 9042.66 ms and left 269.32 s unhidden in one repeat, making net TTFT 138.33% worse than raw. The fused v1 verifier averaged 1347.50 ms in the comparable r1 pair and left 0.54 s unhidden, producing a 17.11% net TTFT reduction. Thus the large v0 overhead was an implementation/estimator defect, not an inherent cost of one typed check.

## Workflow Results

| Workflow | Contract coverage | New-prefill reduction | Net mean TTFT reduction | Quality violations |
| --- | ---: | ---: | ---: | ---: |
| RULER | 100.00% | 84.84% | 47.98% | 0 |
| HotpotQA | 40.00% | 21.06% | 10.21% | 0 |
| NarrativeQA | 40.00% | 19.30% | 10.60% | 0 |
| Qasper | 30.00% | 25.79% | 14.98% | 8 |
| RepoBench | 20.00% | 19.75% | 17.03% | 0 |

All eight policy-attributable violations came from two Qasper sessions admitted by the bounded lexical Tier B. The recurring drops were 0.0606 and 0.1253. Exact-only admitted no unsafe request across the three repeats. The aggregate task score was slightly higher under the contract (+0.0019), but aggregate means do not erase per-request safety failures.

There were also 38 raw-fallback pair differences across fresh processes. They are reported separately and are not attributed to ContractKV because the effective layout was L0 in both cells. Temperature was zero and the seed was fixed; these differences expose cross-process numerical path sensitivity near token ties.

## Physical Evidence

Completion was 100%, scope-invalid admission was zero, and maximum dynamic-suffix reuse was zero. Admitted requests reused 76.46% of their physical prefix blocks on average. RULER reached 85.49% physical reuse and the strongest real result: 84.84% less new-prefill work and 47.98% lower net mean TTFT.

This rules out MLA/MoE cache incompatibility as the global root cause. The same runtime, block observer, prefix cache, and transaction path work on DeepSeek when a layout is certifiable.

## Gate And Diagnosis

The preregistered paper gate did not pass:

- completion, scope, and suffix-isolation gates passed;
- quality violations were 8 rather than 0;
- coverage was 46% rather than at least 50%;
- new-prefill reduction was 28.91% rather than at least 30%;
- net mean TTFT reduction was 18.78% rather than at least 25%.

The failure has two layers. The v0 performance collapse was a code/accounting defect and is fixed. The remaining failure is a certificate-design boundary: token-F1 plus numeric, polarity, and length guards is not a strong behavioral contract for open-ended Qasper, and a Turn-0 output comparison does not prove all future turns safe. Relaxing it further would recreate unsafe admission. Exact-only is safe but remains too conservative to meet the broad performance gate.

## Claim Boundary

Phase 26D establishes real DeepSeek MLA+MoE prefix reuse, a low-overhead fused verifier, and a precise negative boundary for free-form typed certification. It does not establish broad safe DeepSeek generalization. Candidate namespaces are isolated with unique salts and reset before measured traffic; successful layouts are re-prefilled. Typed-candidate KV blocks are not zero-copy promoted in place.
