# Phase 2 Qwen3-8B Baseline Report

## Result

Phase 2 passed on `2026-07-08`.

Server configuration:

- Model: `Qwen3-8B`
- Backend: vLLM OpenAI-compatible API
- Port: `8001`
- GPU: `0`
- Tensor parallel size: `1`
- dtype: `float16`
- GPU memory utilization: `0.88`

Context scaling summary:

| max_model_len | max_num_seqs | Startup | Prompts | Success | Error Types | Avg TTFT ms | Avg TPOT ms | Idle GPU GiB | Peak GPU GiB |
| ---: | ---: | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| 8192 | 2 | true | 3 | 3 | `none` | 266.609 | 21.490 | 20.084 | 20.088 |
| 16384 | 2 | true | 3 | 3 | `none` | 275.621 | 21.455 | 21.020 | 21.059 |
| 32768 | 1 | true | 3 | 3 | `none` | 259.178 | 21.429 | 21.002 | 21.059 |

The 32K run started successfully on a single RTX 3090 with `max_num_seqs=1`. vLLM reported a GPU KV cache size of 38,176 tokens and maximum concurrency of about 1.17x for 32,768-token requests, so this configuration is usable but has little serving headroom.

## Exit Criteria

- Passed: `8192` context length succeeded before trying larger contexts.
- Passed: `16384` was attempted only after `8192` was recorded.
- Passed: `32768` was attempted only after `16384` was recorded.
- Passed: every context length writes machine-readable rows with `error_type`, `log_path`, manifest path, and commit hash.

## Evidence Files

- `results/baselines/model_feasibility.csv`
- `results/baselines/qwen3_8b_context_scaling.csv`
- `logs/phase2/qwen3_8b_8192.log`
- `logs/phase2/qwen3_8b_16384.log`
- `logs/phase2/qwen3_8b_32768.log`
- `results/manifests/phase2_qwen3_8b_*.yaml`
