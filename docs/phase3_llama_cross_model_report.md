# Phase 3 Llama Cross-Model Report

## Status

Llama-3.1-8B Phase 3 light validation is complete.

- Raw runs: 24
- `error_type=none`: 24
- Purpose: cross-model validation, not leaderboard ranking

## Key Finding

The Llama-3.1-8B run shows the same qualitative long-context pressure as Qwen3-8B: TTFT and TPOT both rise as actual prompt tokens increase from 4K to 32K. This supports the claim that the segment lifecycle problem is not Qwen-only.

## Results

| Target tokens | Avg TTFT ms | Avg TPOT ms | Peak GPU mem GiB |
| ---: | ---: | ---: | ---: |
| 4096 | 55.336 | 26.861 | 21.299 |
| 8192 | 81.218 | 27.971 | 21.299 |
| 16384 | 114.369 | 30.123 | 21.299 |
| 32768 | 189.885 | 33.703 | 21.299 |

## Boundary

This is a lightweight cross-model validation using `ruler_haystack` and `longbench_hotpotqa` prompts with three measured repeats. It is not a full benchmark suite.

Detailed artifact report: `docs/phase3_llama3_8b_cross_model_report.md`.
