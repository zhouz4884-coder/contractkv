# Phase 26A: Strict-Failure Recoverability Audit

## Scope

Phase 26A used only the Phase 25 development split. It did not inspect or tune on the new Phase 26 held-out split. For each DeepSeek-V2-Lite Chat/Coder layout candidate at L1-L3, the audit collected a raw free generation, a candidate free generation, official task scores, completion state, typed-contract decision, teacher-forced token regret, and divergence/reconvergence diagnostics.

The audit separates four outcomes: exact pass, exact-path false negative, task-safe but not online-certifiable divergence, genuine unsafe divergence, and protocol unavailable. Offline task scores are used only to estimate the recoverable upper bound; they are never inputs to the online certificate.

## Runtime Correction

The first prompt-logprob audit at `gpu_memory_utilization=0.90` exhausted the remaining workspace while materializing prompt logits. This was a runtime-configuration problem, not evidence against the method: the standard vLLM endpoint attempted an approximately 798 MiB allocation with approximately 547 MiB free. The audit was restarted at the preregistered-compatible `0.70` utilization, retaining TP=2, bfloat16, the model, prompts, decoding rule, and score protocol. All 150 candidate rows then completed.

## Budget-Aware Profiling

Budgets were derived from development raw-output lengths using P99 plus 32 tokens, aligned to 32, bounded to [128, 1024]. Frozen budgets were:

| Model | HotpotQA | NarrativeQA | Qasper | RULER | RepoBench |
| --- | ---: | ---: | ---: | ---: | ---: |
| DeepSeek Chat | 128 | 128 | 1024 | 128 | 672 |
| DeepSeek Coder | 160 | 128 | 384 | 128 | 1024 |

One Chat Qasper and one Coder RepoBench reference still reached the 1024-token cap. They remain protocol-unavailable and are not treated as model-quality failures.

## Recoverability Results

| Model | Exact pass | Exact false negative | Task-safe, not online certified | Genuine unsafe | Protocol unavailable |
| --- | ---: | ---: | ---: | ---: | ---: |
| Chat | 10 | 10 | 40 | 12 | 3 |
| Coder | 20 | 11 | 30 | 7 | 7 |

Among complete non-length strict failures, the offline task-safe fraction was 44/56 (78.57%) for Chat and 32/39 (82.05%) for Coder. This establishes substantial exact-certificate conservatism, but not universal safety: 12 Chat and 7 Coder candidates had a real task-score drop above 0.03.

Token regret also separates the populations imperfectly. Chat exact false negatives had mean maximum regret 0.3625 versus 1.5104 for genuine unsafe divergence; the corresponding mean positive-token fractions were 0.0442 and 0.0914. Coder exact false negatives were almost entirely terminal/path-protocol differences, with mean top-1 match 0.9982. Regret is therefore a useful audit and routing signal, not a standalone safety decision.

## Continuation Gate

Both models passed the development-only Phase 26A continuation gate:

| Model | Non-length safe fraction | Families with >=50% theoretical coverage | Theoretical new-prefill reduction | Conservative net TTFT reduction | Safe complete RepoBench sessions |
| --- | ---: | ---: | ---: | ---: | ---: |
| Chat | 78.57% | 5/5 | 82.50% | 25.01% | 4/5 |
| Coder | 82.05% | 4/5 | 76.15% | 40.14% | 3/5 |

These are development upper bounds, not deployed performance claims. They authorized typed-contract development; they did not authorize a held-out run until the separate frozen online-contract gate passed.

## Conclusion

Phase 25's low broad coverage was caused by two distinct effects. The strict token-path certificate rejected many task-safe generations, while a smaller but material subset was genuinely layout-sensitive. The correct remedy is hierarchical certification with fail-closed typed contracts, not an unconditional top-k or margin relaxation.
