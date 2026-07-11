# Phase 16B Ephemeral Shadow Namespace

## Goal

Phase 16B addresses the cache-safety problem: an unverified shadow candidate
must not populate the global prefix cache. If verification fails, no foreground
request should ever observe the shadow blocks. If verification succeeds, only
the certified stable-prefix blocks should be promoted.

## Method

This is an in-memory transactional KV namespace model. It mirrors the intended
vLLM insertion point but does not patch vLLM's `block_pool` yet. The model keeps:

- a global `cached_block_hash_to_block` table
- `shadow_txns`
- `ephemeral_block_owner`
- per-block owner/hash/allocated state

It runs 1000 randomized commit/abort cycles including normal commit, rollback,
duplicate-hash commit, partial final block, and cancellation.

## Result

| Metric | Value |
| --- | ---: |
| cycles | 1000 |
| block leaks | 0 |
| stale hash pointers | 0 |
| cache-table inconsistencies | 0 |
| transaction metadata leaks | 0 |
| active transactions after run | 0 |
| promotion p95 | 0.219 ms |
| rollback p95 | 0.137 ms |
| gate pass | true |

This supports the core invariant:

- before commit: foreground prefix hit for ephemeral blocks is impossible
- after commit: certified stable blocks become visible
- after abort: the global cache table is unchanged and blocks are reclaimed

## Source-Level Follow-Up

Phase 16E installs the same visibility boundary in vLLM V1 by using its real
`delay_cache_blocks` allocation path. In the Qwen3-4B live run, an aborted
shadow left the global cache entry count unchanged and the identical foreground
probe reused only 0.48% of prompt tokens. A committed shadow registered 246
new full blocks in 0.396 ms, and the identical probe reused 99.85% of prompt
tokens. Both model outputs passed marker sanity.

## Boundary

Commit/rollback is O(B) in the number of promoted/freed blocks, not O(1). The
in-memory result remains a concurrency-model check. Phase 16E is a real vLLM
whole-request stable-prefix transaction, but it does not yet prove concurrent
commit atomicity, multi-KV-group behavior, or an in-situ teacher-forced verifier.

## Artifacts

- `scripts/phase16b_ephemeral_kv_transaction.py`
- `results/runtime/phase16b_ephemeral_kv_transaction_events_v0.jsonl`
- `results/runtime/phase16b_ephemeral_kv_transaction_summary_v0.csv`
