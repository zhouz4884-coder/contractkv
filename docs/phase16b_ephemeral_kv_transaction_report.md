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
| promotion p95 | 0.237 ms |
| rollback p95 | 0.146 ms |
| gate pass | true |

This supports the core invariant:

- before commit: foreground prefix hit for ephemeral blocks is impossible
- after commit: certified stable blocks become visible
- after abort: the global cache table is unchanged and blocks are reclaimed

## Boundary

Commit/rollback is O(B) in the number of promoted/freed blocks, not O(1). The
current result is a correctness and latency model; the next step is to install
the same transaction boundary in vLLM V1 block registration.

## Artifacts

- `scripts/phase16b_ephemeral_kv_transaction.py`
- `results/runtime/phase16b_ephemeral_kv_transaction_events_v0.jsonl`
- `results/runtime/phase16b_ephemeral_kv_transaction_summary_v0.csv`
