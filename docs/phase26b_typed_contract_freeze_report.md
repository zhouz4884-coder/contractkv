# Phase 26B: Typed Contract and Benefit-Gate Freeze

## Frozen Online Interface

Phase 26B converts the offline recoverability opportunity into a reference-free online policy. Runtime admission never uses benchmark answers. It requires:

1. Tier E exact token-path verification, or a deterministic Tier B output contract after Tier E fails.
2. A frozen family/level scope learned only from development data.
3. `SafetyGate AND BenefitGate`; `FAIL`, `UNKNOWN`, incomplete output, timeout, or contract error falls back to L0 raw order.

The contract library is versioned and hashed. RULER uses normalized answer equality. RepoBench accepts exact code fragments or exact canonical ASTs only; AST equality is described as structural equality, not general program equivalence. LongBench bounded lexical matching requires token F1 >= 0.8 plus identical numeric fields, identical polarity markers, and a maximum 2x answer-length ratio. This QA contract is a bounded lexical contract, not a proof of semantic equivalence, and its held-out task score is audited separately.

## Cost Gate

Tier B is enabled per family and layout only when the development estimate

`p_pass * expected_future_reuses * saved_prefill_ms - max(0, verify_ms - tool_slack_ms) > 0`

is positive and development admitted-quality violations are zero. The frozen protocol uses nine future reuses and 6000 ms tool slack. Safety and economic value remain separate decisions.

## Frozen Outcome

| Model | Qualified families | Development global deployable coverage | Held-out gate |
| --- | --- | ---: | --- |
| DeepSeek-V2-Lite-Chat | HotpotQA, RULER | 44% | Closed |
| DeepSeek-Coder-V2-Lite-Instruct | HotpotQA, NarrativeQA, RULER, RepoBench | 60% | Open |

The Chat model did not reach the preregistered three-family and 50% global coverage gate. It was not run on the new sealed held-out. This is an intentional fail-closed boundary rather than hidden negative data.

The Coder manifest hash is `f3e8f368ff4c33abb0920f6ced2841e72c33fe82b8933c23878fc9aa09417ac1`. Qasper is frozen unqualified and always uses raw order. The new split contains 50 sessions, ten per family, with zero sample/source-group overlap against development and previous held-out data. Its commitment SHA-256 is `2f31fb7fcf7b0e5507c49d386c6af28f741e2d100b15ffa04cd59f9cbd127e38`.

## Claim Boundary

Phase 26B proves a prospective policy freeze. It does not claim that every task-safe offline candidate is online certifiable, that free-form lexical F1 is semantic equivalence, or that the Chat model broadly generalizes. Only the Coder policy proceeded to sealed evaluation.

## Fused-Verifier Amendment

The first Coder held-out diagnostic exposed an implementation error in the v0 economic gate: it selected multiple exact/typed descent attempts but did not charge their cumulative runtime. That run is retained as an invalidated-estimator diagnostic, not a paper result. Its observed mean TTFT fell by 27.96%, but net mean TTFT increased by 138.33% after the omitted cost was charged.

Before completing the held-out matrix, a development-only fused verifier was frozen. It evaluates one layout candidate, applies exact identity first and the typed contract second, and enforces a 6000 ms hard deadline. The new qualification hash is `7250e1216dcb25d8b40186a3c47aeb569fb2d52dc70c1b515d5fe06cbdf6cdfd`. The source-group-disjoint split commitment is `31397988f5dd1f0ba0a8758d39c9f657bf6b9e85f9fc15cc2a447ba6b4445b9a`.

The fused development optimizer selected HotpotQA L2, NarrativeQA L2, Qasper L3, RULER L3, and RepoBench L3 with 52% estimated development coverage. This amendment fixed the cost accounting, but it did not strengthen the semantics of the QA lexical contract or use held-out task scores.
