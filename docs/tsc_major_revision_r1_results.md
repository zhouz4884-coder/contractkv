# TSC Major Revision R1: Completed Experimental Evidence

This report follows X1-X7 in the frozen revision plan. Experiment completion is distinct from scientific success. The submitted manuscript has not been overwritten; this is an experimental evidence package, not a submitted revision.

## X1. Identical Non-RULER Common Scope

All models consume the same 30 source-disjoint HotpotQA sessions, fixed L2 segment order, 10 turns, 128-token budget, concurrency 2, and three fresh raw/ContractKV process pairs. All runtime rejections remain in the denominator.

| Model | Paired futures | Coverage | New-prefill reduction | Observed mean TTFT ms | Net reduction, slack 0 | Net, 2s | Net, 6s | Drops >0.03 |
|---|---|---|---|---|---|---|---|---|
| qwen | 810 | 63.33% | 48.05% | 1082.7 -> 579.7 | 9.03% | 29.56% | 46.46% | 0 |
| mistral | 810 | 53.33% | 40.69% | 1139.9 -> 706.1 | 0.54% | 20.04% | 37.71% | 0 |
| llama | 810 | 50.00% | 38.38% | 1036.7 -> 624.9 | 6.15% | 27.59% | 39.72% | 0 |

The non-RULER mechanism generalizes, but its global effects do not converge as tightly as the RULER scope. The 0/2/6s columns are amortized residual-cost accounting, not measured scheduler overlap. At zero slack, the fixed-model macro interval crosses zero; it is not evidence of universal cold-session speedup.

| Slack ms | Fixed-three-model net mean reduction | Joint-session 95% CI |
|---|---|---|
| 0 | 5.24% | [-2.16%, 12.56%] |
| 2000 | 25.73% | [18.42%, 33.15%] |
| 6000 | 41.30% | [35.37%, 47.45%] |

The bootstrap resamples the same source sessions jointly across models and fresh repeats within model (10,000 draws). It estimates the average effect for these three fixed models, not an architecture-population prediction interval.

## X2. Actual Free-Running Generation and Output Horizon

Each model executes 50 new source-disjoint benchmark-derived sessions (10 per family), three fresh paired repetitions, and nine futures per session. The original family budgets and an independently rebound 512-token budget are separate conditions. Every future has actual vLLM output token IDs, a request-metric join, and a frozen task score. This diagnostic tries one frozen maximum level and then raw fallback; it does not execute the original adaptive eligible-level descent or benefit gate. Its generic task instruction and context/output settings are therefore not a reproduction of the complete published end-to-end policy.

| Model | Budget | Pairs | Token divergences | Drops >0.03 | Mean score raw -> C | Raw length stops |
|---|---|---|---|---|---|---|
| llama | native | 1350 | 21 | 9 | 0.38400 -> 0.38436 | 108 |
| llama | 512 | 1350 | 18 | 9 | 0.38379 -> 0.38413 | 84 |
| mistral | native | 1350 | 22 | 11 | 0.34742 -> 0.34703 | 9 |
| mistral | 512 | 1350 | 25 | 11 | 0.34736 -> 0.34692 | 0 |
| qwen | native | 1350 | 132 | 38 | 0.35282 -> 0.35787 | 0 |
| qwen | 512 | 1350 | 128 | 36 | 0.35287 -> 0.35792 | 0 |

There are **108 material drops among 3672 admitted future pairs** across the two budget conditions. These are future-scope robustness counterexamples, not zero regression. The cases are correlated within sessions and repeats, not independent failures. The global mean score drop remains very small or negative, but it must not replace the per-request tail-risk table.

| Model/family | Distinct affected sessions |
|---|---|
| llama/NarrativeQA | 1 |
| mistral/NarrativeQA | 1 |
| qwen/Qasper | 1 |
| qwen/RepoBench | 1 |

### Root-Cause Separation

- In the three-model free-generation matrix, all compiled material drops occur on turns with new query wrappers (turns 1/2/4/5/7/8); none occur on the unwrapped-query turns 3/6/9. Repeated raw scores in the substantive cases are stable. Raw-vs-raw controls exhibit much less variation, so the main failures cannot be dismissed as numerical noise.
- The code checks stable-prefix identity and generation budget, but does not turn a Turn-0 path certificate into a proof for a changed query. The defect is an insufficient future-input scope gate if such a certificate is consumed as an arbitrary-query guarantee. The conceptual boundary is that teacher-forced equivalence for one prompt does not imply equivalence for all future prompts.
- Qasper includes an expression-length/F1 effect; RepoBench includes changed code completions and NarrativeQA changed answer content. Official thresholded scores are retained; benign-looking wording is not silently reclassified as a pass.
- Prefix promotion itself passed: no accepted length-stop reference, no commit beyond the stable-only boundary, and no publication on rejected verification. This separates correct physical publication from overly broad behavioral scope.
- No held-out family/layout/threshold was retuned and no success subset replaces the global denominator. A deployment repair must prospectively bind allowed query/suffix transformations or reattest new scopes; that repair's performance has not been measured in this frozen matrix.

| Experiment/model | Budget | Raw-repeat comparisons | Token divergences | Score abs diff >0.03 |
|---|---|---|---|---|
| common-hotpot/llama | 0 | 810 | 2 | 0 |
| common-hotpot/mistral | 0 | 810 | 6 | 0 |
| common-hotpot/qwen | 0 | 810 | 4 | 0 |
| free-generation/llama | 0 | 1350 | 6 | 2 |
| free-generation/llama | 512 | 1350 | 4 | 0 |
| free-generation/mistral | 0 | 1350 | 4 | 2 |
| free-generation/mistral | 512 | 1350 | 8 | 2 |
| free-generation/qwen | 0 | 1350 | 16 | 8 |
| free-generation/qwen | 512 | 1350 | 16 | 8 |
| qwen14-full-cost/qwen14 | 96 | 675 | 4 | 4 |

Raw comparisons pair repeats 1-2, 1-3 and 2-3, so each request participates three times. They provide a control distribution, not causal exoneration of individual fallback mismatches.

### Horizon Boundary

Among the 3672 admitted free-running pairs, 0 pairs actually exceed 96 output tokens. The 512 cap therefore tests an extended generation binding and length-stop handling, **not 512-token positive certified behavior**. Original main canaries did not archive their direct free-output token IDs; later futures did. The exact main source snapshot is retained, and this logging omission is not filled with inferred tokens.

### Measured positions beyond the actual witness length

A followup over the immutable R1 raw records finds 216/3672 admitted free-generation futures longer than their own Turn-0 raw reference, totaling 2376 returned token positions beyond that reference length. These positions are reported separately and are not labelled certified. Requests share sources and repeats, and the two budget conditions are correlated. Counts include the terminal stop when returned.

| Model | Budget condition | Compiled futures | Reference length range | Future max | Longer outputs | Extra positions |
|---|---|---|---|---|---|---|
| Llama-3.1-8B-Instruct | b0 | 567 | 2–55 | 96 | 27 | 558 |
| Llama-3.1-8B-Instruct | b512 | 567 | 2–55 | 96 | 27 | 558 |
| Mistral-7B-Instruct-v0.3 | b0 | 378 | 3–20 | 31 | 18 | 189 |
| Mistral-7B-Instruct-v0.3 | b512 | 378 | 3–20 | 31 | 18 | 189 |
| Qwen3-8B | b0 | 891 | 7–80 | 80 | 63 | 441 |
| Qwen3-8B | b512 | 891 | 7–80 | 80 | 63 | 441 |

The original main retained reference lengths/hashes but no direct reference token IDs, so first divergence from that witness is unavailable. The raw-versus-compiled future-pair divergence still uses actual returned IDs. Even within the length bound, a changed token history is not covered by the original teacher-forced path. This followup changes no admission, task score or original raw record. Per-request evidence is in `results/tsc_revision_r1/output_horizon_pairs_v1.csv`; the separately versioned producer is `scripts/tsc_revision_r1r_output_horizon.py`.

## X3. Complete Verification Cost and Live Zero-Slack Service

Historical archived timing is audited without inventing missing reference or rejected-attempt clocks. Fresh R1 registration clocks include reference decode, token preparation and verification for both accepted and rejected sessions. The TP2 14B experiment is a fresh cost supplement, not a reconstruction of the earlier 44.69% result. The following session table measures the R1 maximum-level diagnostic variant; it does not substitute for missing exact historical clocks.

| Fresh model | Futures | Registration ms/session | Full cost ms/future | Zero-slack net TTFT reduction |
|---|---|---|---|---|
| qwen | 1350 | 3791.8 | 421.3 | 17.50% |
| mistral | 1350 | 1925.5 | 213.9 | -2.84% |
| llama | 1350 | 1608.6 | 178.7 | 7.69% |
| qwen14 | 675 | 4843.7 | 538.2 | 10.59% |

A complementary within-family result is strong even with all registration charged and no slack. The RULER rows below are a labelled scope subset of the same frozen matrix; they do not replace the five-family global result.

| Model | Native-budget RULER futures | Observed mean TTFT ms | Full-cost zero-slack net reduction |
|---|---|---|---|
| qwen | 270 | 567.0 -> 72.8 | 40.57% |
| mistral | 270 | 568.1 -> 65.3 | 46.65% |
| llama | 270 | 518.4 -> 66.3 | 47.63% |

The service replay has 20 tenants across five frozen templates, 180 actual future task requests per cell, Poisson arrivals at 1.6 requests/s, max_num_seqs=2, and three fresh processes per policy/model. The verifier uses the same vLLM engine. Full registration plus business warming is charged to wall-clock goodput; nothing is subtracted as imaginary overlap.

| Model | Policy | Observed mean TTFT ms | Observed p99 ms | Cold-inclusive 1500ms goodput req/s | Registration+warmup s | Drop rate | New-prefill tokens |
|---|---|---|---|---|---|---|---|
| mistral | D0-native-apc | 39217.1 | 75734.3 | 0.010 | 8.12 | 0.00% | 2541.7 |
| mistral | D1-frozen-safe | 13364.7 | 24803.9 | 0.045 | 8.23 | 0.00% | 1240.7 |
| mistral | D2-template-contractkv | 24784.4 | 44729.7 | 0.011 | 17.22 | 0.00% | 1756.2 |
| qwen | D0-native-apc | 2694.3 | 6735.9 | 0.425 | 4.05 | 0.00% | 2239.0 |
| qwen | D1-frozen-safe | 216.6 | 934.6 | 1.443 | 4.06 | 0.00% | 445.0 |
| qwen | D2-template-contractkv | 218.0 | 933.5 | 1.307 | 17.00 | 0.00% | 445.0 |

Request TTFT begins after registration at actual submission. Cold-start delay is included in the end-to-end goodput denominator, not hidden in a claimed per-request p99. Client prompt preparation and server startup precede the declared interval. Verifier HTTP calls are counted from server logs, excluding the guard probe and separately from planned registration attempts.

| Model/policy | Quality pairs | Compiled | Drops >0.03 | Mean score raw -> policy |
|---|---|---|---|---|
| mistral/D1-frozen-safe | 540 | 324 | 0 | 0.27086 -> 0.27086 |
| mistral/D2-template-contractkv | 540 | 216 | 0 | 0.27086 -> 0.27086 |
| qwen/D1-frozen-safe | 540 | 432 | 0 | 0.35600 -> 0.35600 |
| qwen/D2-template-contractkv | 540 | 432 | 0 | 0.35600 -> 0.35600 |

## X4. Value of Certification Beyond Layout-Only Serving

The same legal declared-DAG candidate set contains 20 controlled prompts. Of 10 candidates that actually reduce the task score, 10 are rejected. Rejected publication totals 0 tokens. Raw and candidate outputs, the actual verifier decision, and commit state are retained.

This is a controlled instruction-order negative control, not a benchmark aggregate. The score strips only a reasoning wrapper and accepts the exact requested color. A dependency graph declared by the caller can omit a semantic constraint; the behavioral verifier is useful precisely in that case.

The initial Qwen3-8B probe's effective score is a routing-accounted value from already generated raw/candidate outputs, not a new post-decision generation. It demonstrates actual rejection and transaction-scoped zero publication. A supplementary probe closes that final output step with fresh business requests.

D1 is an offline frozen-safe reference without online attestation; D2 adds evidence-bound shared-state admission. D2 is not required to beat D1's latency. Its claimed benefit is rejecting unsafe promotion while retaining useful reuse on accepted scopes.

The supplementary qwen3-14b TP2 probe executes 20 fresh post-decision business outputs. It rejects 10/10 genuinely bad candidates; all protected scores equal raw: True. Rejected publication: 0 tokens. This supplemental probe runs only after a main cell's raw file and timing summary are finalized, and does not enter that cell's future-count or wall-time denominator.

## X5. Manifest Correctness and Isolation Boundary

The 9-case CPU registration validator rejects untrusted issuer/role, stale signatures/hashes, missing authorization/version, and explicitly private or mutable publication. All expected outcomes match. A correctly signed trusted-operator declaration that mislabels private content as public is deliberately accepted: hashes establish byte identity, not confidentiality. This is an explicit trust boundary, not a claimed live confidentiality defense.

The R1 endpoint is operator-internal and bound to localhost. Shared-prefix authorization does not eliminate hit-timing inference within an authorized domain. The prototype does not implement a prefix-cache timing-channel defense.

## X6. Baseline Fairness, Statistics and Input Differences

| Method | Native paired baseline | Pairs | Mean score raw -> method | Material drops | Material improvements |
|---|---|---|---|---|---|
| cacheblend | cacheblend_raw | 2250 | 0.33321 -> 0.33982 | 224 | 331 |
| contractkv | vllm_apc | 2250 | 0.35378 -> 0.35374 | 2 | 0 |
| manual_oracle | vllm_apc | 2250 | 0.35378 -> 0.35632 | 39 | 60 |
| sglang_certified | sglang_raw | 2250 | 0.35374 -> 0.35387 | 2 | 2 |

CacheBlend's aggregate quality improvement and per-request regressions can coexist. Its original study reports aggregate F1/Rouge on different models and datasets, not this workload's >0.03 per-request statistic. Threshold sensitivity (0.01/0.03/0.05) and family-level improvements/regressions are supplied. Neither 112x causal safety nor 2.18% cross-stack performance superiority is asserted.

The exact frozen-tokenizer input analysis retains 4,695 segment observations: raw/candidate order index, token position, displacement, prompt length and render-token identity. Stable context is moved before the volatile observation when the frozen layout permits it. These are measured input differences, not claims about RoPE or attention as an architectural root cause.

## X7. Reproducibility and Completion

Required live cells completed: **78/78**. Measured futures: **25650/25650**. Raw hashes, request identities, complete registration clocks, actual token evidence, metric joins and rejected-publication invariants are checked on the authoritative remote raw root. Private credential archives are not part of the public package.

The actual executed main source is SHA-verified in `source_snapshots/tsc_revision_live_main_v1.py`; later logging-only additions are separately identified. The serving patch is archived against official vLLM v0.10.2, alongside package versions and the non-test result-code inventory. Superseded boundary/startup attempts remain quarantined and excluded from formal tables.

## Scientific Bottom Line

The physical reuse and fail-closed publication mechanism remain supported. The non-RULER common scope is a positive mechanism test. The broader unseen-query-wrapper free-generation test exposes a real future-scope boundary; it cannot be presented as globally zero regression. Cold-session verification economics are weaker than slack-accounted or high-fan-out service results. These distinctions should strengthen the revised paper's argument by making its scope enforceable, not be hidden behind only the best numbers.
