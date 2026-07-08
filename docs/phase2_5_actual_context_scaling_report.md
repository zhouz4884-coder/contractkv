# Phase 2.5 Actual Context Scaling Report

This report is generated from `results/baselines/qwen3_8b_actual_context_scaling_raw.csv` and `results/baselines/qwen3_8b_actual_context_scaling_summary.csv`.

Phase 2.5 measures real prompt lengths after the Qwen chat template is applied. It must be interpreted separately from Phase 2, which only measured `configured_max_model_len` feasibility with short prompts.

## Result

Phase 2.5 completed with 80 raw runs: 4 target lengths x 4 prompt sources x 5 repeats.

| target tokens | configured max len | avg TTFT ms | avg TPOT ms | peak GPU GiB |
| ---: | ---: | ---: | ---: | ---: |
| 4096 | 8192 | 59.452 | 22.225 | 21.262 |
| 8192 | 16384 | 82.057 | 23.113 | 21.260 |
| 16384 | 32768 | 122.138 | 24.869 | 21.260 |
| 32768 | 33792 | 199.988 | 28.283 | 21.260 |

All raw runs returned `error_type=none`. The 8K, 16K, and 32K prompt tests intentionally use `configured_max_model_len` larger than `actual_prompt_tokens_after_chat_template` so that `generation_max_tokens=128` fits inside the serving context.

Prompt sources:

- `synthetic_repeat`: low-entropy sanity check.
- `ruler_haystack`: RULER-style synthetic haystack.
- `longbench_hotpotqa`: LongBench-style text prompt generated from fallback/source-derived text because HuggingFace download was unavailable.
- `repobench_code`: RepoBench-style code prompt generated from fallback/source-derived code text because HuggingFace download was unavailable.
