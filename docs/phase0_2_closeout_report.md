# Phase 0-2 Closeout Report

## Status

Phase 0-2 is closed as the feasibility baseline for ContractKV.

- Phase 0 passed: CUDA 12.8, PyTorch 2.8.0+cu128, vLLM 0.10.2, and two RTX 3090 GPUs are available.
- Phase 1 passed: Qwen3-4B served through vLLM and all three smoke prompts returned with `error_type=none`.
- Phase 2 passed as a Qwen3-8B `max_model_len` feasibility baseline: 8192, 16384, and 32768 all started and completed short-prompt stream TTFT/TPOT checks.

## Caveat

Phase 2 does not prove full-context prefill scaling. It proves that Qwen3-8B can be configured with the requested `max_model_len` values and can answer short prompts through the OpenAI-compatible stream API.

The next characterization stage must separately measure `actual_prompt_tokens_after_chat_template` at 4K, 8K, 16K, and 32K.

## Key Observation

Qwen3-8B can run with `max_model_len=32768` on a single RTX 3090, but vLLM reports only about `1.17x` maximum concurrency for 32,768-token requests. Long-context serving is feasible on this hardware, but capacity headroom is tight.

## Next Batch

`characterization_batch_001` will add:

- Phase 2.5 actual input-token context scaling.
- Phase 2.6 Host/GPU transfer and copy/decode interference microbenchmarks.
- Phase 2.7 RULER, LongBench, and RepoBench dataset readiness with a unified segment schema.
