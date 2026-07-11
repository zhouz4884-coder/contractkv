# Phase 16E Real vLLM Transactional Shadow Hook

## Goal

Phase 16E moves the two strongest Phase 16 mechanisms into vLLM 0.10.2 V1:

1. an IDLE_ONLY shadow request is capped to a small token slice at both waiting
   admission and subsequent running rounds;
2. shadow KV blocks use vLLM's real `delay_cache_blocks` path and remain outside
   global prefix-cache hash registration until commit.

The hook is opt-in through `CONTRACTKV_EPHEMERAL_SHADOW=1`. Normal requests keep
the original vLLM path.

## Setup

- model: Qwen3-4B, FP16, one RTX 3090
- vLLM: 0.10.2 V1, prefix cache enabled, priority scheduling
- max model length: 8192
- max sequences: 8
- active workload: 3 seeds, 30 measured requests per seed and condition
- shadow workload: 2 long shadow requests per seed
- fairness: 5 condition-local warmups and disjoint prompt namespaces

## Micro-Chunk Result

The valid fair runs cap both initial admission and running rounds. Earlier
running-only measurements are superseded because their first shadow allocation
could schedule 2048 tokens.

| Chunk | Condition | Success | Mean TTFT | p95 TTFT | p95 delta |
| ---: | --- | ---: | ---: | ---: | ---: |
| 16 | baseline | 90/90 | 32.36 ms | 39.01 ms | - |
| 16 | IDLE_ONLY shadow | 90/90, shadow 6/6 | 40.72 ms | 49.96 ms | +10.96 ms |
| 32 | baseline | 90/90 | 32.38 ms | 37.69 ms | - |
| 32 | IDLE_ONLY shadow | 90/90, shadow 6/6 | 41.12 ms | 49.59 ms | +11.91 ms |

The source-level hook reduces the previous Phase 15D p95 penalty from roughly
585 ms to about 11 ms, but neither 16 nor 32 tokens strictly passes the preset
10 ms gate. The weak dependence on chunk size suggests the remaining cost is
dominated by scheduling-round/kernel-launch overhead rather than token-linear
prefill cost. This is a useful hard boundary, not a pass.

## Ephemeral Transaction Result

The abort and commit probes use unique prompts followed by an identical normal
foreground request.

| Action | Stable tokens | Cache entries delta | Foreground reuse | Operation |
| --- | ---: | ---: | ---: | ---: |
| abort | 3358 | 0 | 0.48% | 0.003 ms |
| commit | 3958 | +246 | 99.85% | 0.396 ms |

Before finalize, only one inherited common-prefix block was visible; the newly
allocated shadow blocks were unregistered. Abort left the global cache table
unchanged. Commit registered 246 full blocks, and the next request reused the
committed prefix. Both shadow and foreground outputs passed marker sanity.

## What This Proves

- real vLLM physical blocks can be allocated without global prefix visibility;
- abort prevents failed shadow work from polluting the prefix cache;
- commit publishes verified stable-prefix blocks that a later request can hit;
- IDLE_ONLY token slicing removes most, but not all, active-tenant interference.
- the same vLLM backend exposes candidate teacher-forced top-1 ranks; the
  companion 12-case probe matched all 146 answer tokens.

## Boundary

This is a whole-shadow-request stable-prefix transaction. It does not yet prove
concurrent transaction atomicity, partial-block promotion, tensor-parallel
consistency, or an in-situ teacher-forced verifier. The micro-chunk interference
gate remains failed by 0.96-1.91 ms and must not be reported as zero-cost.

## Artifacts

- `scripts/install_vllm_v1_ephemeral_shadow_hook.py`
- `scripts/phase16e_live_transactional_slc.py`
- `scripts/run_phase16e_live.sh`
- `scripts/phase16c_vllm_teacher_forced_probe.py`
- `results/hard_systems/phase16c_vllm_teacher_forced_probe_v0.csv`
- `results/hard_systems/phase16e_qwen3_4b_fair_fullcap_chunk16_interference_raw_v0.csv`
- `results/hard_systems/phase16e_qwen3_4b_fair_fullcap_chunk32_interference_raw_v0.csv`
- `results/hard_systems/phase16e_qwen3_4b_live_ephemeral_transaction_v0.csv`
- `results/hard_systems/phase16e_qwen3_4b_transaction_events_v0.jsonl`
