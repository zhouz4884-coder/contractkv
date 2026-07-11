# Phase 15C Cache-State Adaptation

## Goal

Phase 15C tests whether CAPOSC needs physical cache-state feedback, not only a
logical segment ledger. The target conflict is simple: two layouts have the same
semantic legality, but the previous request's physical prefix-cache state favors
one of them. A deployable compiler should prefer the physically resident layout.

## Qwen3-8B Conflict Result

The Qwen3-8B replay uses three fresh-process seeds and 100 turns per policy.
Physical-residency CAPOSC keeps the selected prefix within one block of the
native vLLM residency signal on every turn.

| Policy | Turns | Mean TTFT | p95 TTFT | Mean prefix hit | Mean new prefill |
| --- | ---: | ---: | ---: | ---: | ---: |
| raw-order | 300 | 1,046 ms | 1,059 ms | 16 tokens | 4,143 tokens |
| static-posc | 300 | 1,046 ms | 1,061 ms | 29 tokens | 4,130 tokens |
| logical-ledger-caposc | 300 | 1,047 ms | 1,063 ms | 29 tokens | 4,130 tokens |
| physical-residency-caposc | 300 | 570 ms | 579 ms | 2,080 tokens | 2,079 tokens |

Relative to static POSC, physical-residency CAPOSC reduces mean TTFT by 45.45%,
p95 TTFT by 45.41%, and new-prefill tokens by 49.66%. Quality sanity remains
100% for every policy.

## Qwen3-4B Replication

The same conflict was rerun on Qwen3-4B across three fresh-process seeds.

| Policy | Turns | Mean TTFT | p95 TTFT | Mean prefix hit | Mean new prefill |
| --- | ---: | ---: | ---: | ---: | ---: |
| static-posc | 300 | 649 ms | 656 ms | 29 tokens | 4,129 tokens |
| physical-residency-caposc | 300 | 375 ms | 382 ms | 2,080 tokens | 2,079 tokens |

This second-model replication supports the interpretation that the benefit is a
real cache-state effect rather than a single-model timing accident.

## Native Block-Hash Churn Probe

The vLLM V1 prefix metrics probe was extended with a read-only candidate
residency query over native `cached_block_hash_to_block` state. Across three
Qwen3-8B churn seeds and ten pollution cycles per seed:

- switch within one round: 100%
- selected prefix within one block: 100%
- maximum continuous stale rounds: 0
- quality sanity: 100%
- mean TTFT after adaptation: 68.4 ms

This proves that the compiler can observe and react to changing native cache
state. It does not claim arbitrary pre-request multi-candidate RPC support or
real KV placement control.

## Boundary

The actuator remains a layout compiler plus read-only cache-state observer. It
uses prior-request physical feedback and native block-hash residency, but it
does not move KV blocks or mutate vLLM's block manager.

## Artifacts

- `results/hard_systems/phase15c_cache_conflict_summary_v0.csv`
- `results/hard_systems/phase15c_qwen3_4b_summary_v0.csv`
- `results/hard_systems/phase15c_cache_churn_raw_v0.csv`
- `results/hard_systems/phase15c_cache_churn_summary_v0.csv`
- `scripts/phase15c_cache_state_conflict.py`
- `scripts/phase15c_cache_churn.py`
- `scripts/install_vllm_v1_prefix_metrics_probe.py`
