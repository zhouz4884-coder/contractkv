# Characterization Batch 001 Closeout

## Status

`characterization_batch_001` is closed for Qwen3-8B characterization.

Completed stages:

- Phase 0-2 closeout: environment, Qwen3-4B smoke, and Qwen3-8B `configured_max_model_len` feasibility are complete.
- Phase 2.5: Qwen3-8B actual input-token context scaling is complete for 4K, 8K, 16K, and 32K targets.
- Phase 2.6: H2D/D2H/P2P bandwidth and copy/decode interference microbenchmarks are complete.
- Phase 2.7: RULER, LongBench, and RepoBench readiness is complete through the offline dataset bundle route.

## Main Results

Phase 2.5 used stream-mode OpenAI-compatible requests with `warmup=1`, `repeat=5`, `temperature=0`, `max_num_seqs=1`, and post-chat-template token accounting. All 80 raw Qwen3-8B runs completed with `error_type=none`.

| Target tokens | Avg TTFT ms | Avg TPOT ms | Peak GPU mem GiB |
| ---: | ---: | ---: | ---: |
| 4096 | 59.452 | 22.225 | 21.262 |
| 8192 | 82.057 | 23.113 | 21.260 |
| 16384 | 122.138 | 24.869 | 21.260 |
| 32768 | 199.988 | 28.283 | 21.260 |

Phase 2.6 transfer measurements show host/device copy bandwidth around 13.2 GB/s at the largest block sizes. The warmed decode proxy increased from 0.282 ms to about 5.37 ms when overlapped with H2D or D2H copy, so later ContractKV placement work should treat transfer scheduling as a first-class decision rather than background noise.

Phase 2.7 dataset readiness now has:

| Dataset | Status | Samples |
| --- | --- | ---: |
| RULER | ready | 20 |
| LongBench | ready | 100 |
| RepoBench | ready | 20 |
| BFCL | missing_optional | 0 |

## Boundaries

Phase 2 proved `configured_max_model_len` feasibility. Phase 2.5 proved actual prompt prefill scaling for generated characterization prompts. Neither phase is an official benchmark score for RULER, LongBench, or RepoBench.

RepoBench samples are explicitly marked `evaluation_ready=false`; they are valid for segment extraction and risk profiling, not pass/fail code benchmark reporting.

## Reproducibility

Large inputs live on the 8T disk:

- Dataset bundle: `/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/datasets/sources/contractkv_datasets.zip`
- Extracted bundle: `/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/datasets/contractkv_datasets`
- HF cache path: `/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/datasets/contractkv_datasets/hf_cache`

The Git repository tracks only lightweight code, configuration, reports, manifests, CSV, and JSONL artifacts.
