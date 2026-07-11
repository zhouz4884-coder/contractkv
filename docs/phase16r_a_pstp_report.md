# Phase 16R-A: Prefix-Selective Transactional Promotion

## Objective

Phase 16R-A replaces the Phase 16 request-ID convention with an explicit, frozen
`PSTPSpec` attached to the vLLM V1 `Request`. The harness may supply a decision,
but only `VerifyDecision.PASS` can register blocks. `FAIL`, `INCOMPLETE`, and
`CANCELLED` all fail closed. Automatic verifier-to-PSTP wiring remains Phase 17.

## Implementation

- `PSTPSpec` is loaded from an atomic request registry and attached as
  `request.contractkv_pstp`; neither `commit` nor `abort` is parsed from the ID.
- The stable boundary is the token-ID LCP of the independently templated stable
  and candidate messages.
- The commit boundary is `floor(min(LCP, num_computed_tokens) / block_size)`.
- Finalization runs before native connector/KV cleanup and is idempotent.
- PSTP calls `cache_blocks(request, commit_tokens)` only. It never manually frees
  suffix blocks.

## Live Result

The live Qwen3-4B run used vLLM 0.10.2, block size 16, prefix caching, and a
single RTX 3090. All six gates passed.

| Case | Decision | Commit tokens | New cache entries | Stable-block reuse | Dynamic reuse |
|---|---:|---:|---:|---:|---:|
| pass | PASS | 5,776 | 361 | 100% | 0 |
| fail | FAIL | 0 | 0 | 0% | 0 |
| incomplete | INCOMPLETE | 0 | 0 | 0% | 0 |
| cancelled | CANCELLED | 0 | 0 | 0% | 0 |
| idempotence | PASS | 6,208 | 387 | 100% | 0 |
| glue | PASS | 6,624 | 413 | 100% | 0 |

The idempotence case committed 388 full blocks but added 387 new entries because
one common block was already visible. The second finalize produced exactly one
duplicate event and no second mutation. Abort probes observed one inherited
16-token common block; after accounting for it, transaction-specific dynamic
suffix reuse was zero.

The glue case measured an expected stable length of 6,629 tokens and an LCP of
6,627. PSTP committed only 6,624 aligned tokens, so the two-token template glue
shift and the final partial block were not over-promoted.

Machine-readable evidence is in
`results/hard_systems/phase16r_pstp_live_v0.csv`.

## Claim Boundary

This validates explicit, prefix-selective block registration and fail-closed
cleanup in the real vLLM V1 scheduler path. It does not yet validate an automatic
live verifier decision driving PSTP, concurrent multi-transaction isolation, or
production fault recovery.
