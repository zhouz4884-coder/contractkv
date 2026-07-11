# Phase 14M Cross-Session Physical Deduplication

## Setup

The experiment uses one RTX 3090, Qwen3-8B, vLLM V1 prefix caching, `max_model_len=8192`, and a shared enterprise-style stable context. Every session has a distinct tool observation and query. Raw order places the observation before the shared context; CAPOSC places the stable context in a legal canonical prefix. Metrics come from live V1 request block tables and scheduler observations.

## Core 4K/16-Session Result

| Policy | Mean TTFT | p95 TTFT | Used-block high-water | Min free blocks | Quality sanity |
| --- | ---: | ---: | ---: | ---: | ---: |
| Raw order, warm | 8,905 ms | 15,418 ms | 1,302 | 12 | 100% |
| CAPOSC, warm | 366 ms | 556 ms | 284 | 1,030 | 100% |
| Raw order, cold | 8,883 ms | 15,706 ms | 1,302 | 12 | 100% |
| CAPOSC, cold | 1,313 ms | 1,485 ms | 284 | 1,030 | 100% |
| CAPOSC + singleflight | 358 ms | 538 ms | 284 | 1,030 | 100% |

For warm 4K fan-out, CAPOSC reduces used-block high-water by 78.2% and p95 TTFT by 96.4% versus raw order. Cold CAPOSC already benefits from rapid cache fill; singleflight removes the remaining fill race and restores the warm-level result.

## Scaling Result

At 6K shared context and 20 sessions, raw order reaches 30.76 s p95 TTFT with 1,286 used blocks and only 28 free blocks. CAPOSC records 0.987 s p95 TTFT, 412 used blocks, 902 free blocks, and an effective physical dedup factor of 17.45x. All 20 requests passed marker sanity.

The main physical metric is not process VRAM. vLLM preallocates its KV arena, so the evidence uses scheduler-observable block high-water, free-block minimum, reused physical block IDs, and logical-to-effective-physical deduplication.

## Artifacts

- `scripts/phase14m_physical_dedup.py`
- `results/hard_systems/phase14m_core_summary_v1.csv`
- `results/hard_systems/phase14m_scaling_summary_v2.csv`
