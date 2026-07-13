# Phase 20C: Two-Tier Transactional Development

## Protocol

Tier 1 uses the frozen cheap certificate. Rejected sessions may enter an ephemeral Tier 2 candidate execution. Tier 2 can promote only after an exact, task-specific contract succeeds; otherwise candidate state is aborted without cache registration. Ground-truth answers are never used online.

The deterministic contracts are RULER exact retrieval, LongBench exact final-answer extraction, and RepoBench AST or normalized-fragment exact agreement. Fuzzy semantic scoring is deliberately excluded.

## Development result

- Development sessions: 25, disjoint from the sealed heldout set.
- Tier 1 certificates: 12 (48%).
- Tier 2 attempts: 13.
- Exact Tier 2 passes and promotions: 0.
- Candidate p95: 8,277.833 ms.
- Promotion-only p95 probe: 6,122.902 ms.
- Frozen incremental budget including guard: 14,500.735 ms.
- Candidate and promotion-probe abort cleanliness: 100%.

Because the frozen budget does not fit the 3 s tool-slack envelope, the heldout policy disables Tier 2. The transaction mechanism is correct, but the proposed full-candidate-plus-promotion execution is not deployable under this slack budget.

## Root cause

This is primarily an algorithmic cost problem, not Python bookkeeping overhead: the protocol performs a full candidate prefill and then a separate promotion prefill. Exact task contracts also provide little rescue coverage. A future design would need incremental verification or state reuse, but Phase 20 freezes here and does not retune on heldout data.
