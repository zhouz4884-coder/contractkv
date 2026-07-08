# Phase 3 Llama-3.1-8B Cross-Model Check

## Status

Phase 3 cross-model characterization is complete for `Llama-3.1-8B-Instruct` as a lightweight validation run.

This is not a full benchmark. It checks whether the actual-context scaling phenomenon observed on Qwen3-8B also appears on a non-Qwen 8B model.

## Configuration

- Model: `/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Llama-3.1-8B-Instruct`
- Served name: `llama3-8b`
- Backend: vLLM 0.10.2
- GPU: single RTX 3090
- dtype: `float16`
- tensor_parallel_size: 1
- gpu_memory_utilization: 0.88
- max_num_seqs: 1
- temperature: 0
- warmup: 1
- repeat: 3
- prompt sources: `ruler_haystack`, `longbench_hotpotqa`

## Results

All 24 raw runs completed with `error_type=none`.

| Target tokens | Configured max_model_len | Avg TTFT ms | Avg TPOT ms | Peak GPU mem GiB |
| ---: | ---: | ---: | ---: | ---: |
| 4096 | 8192 | 55.336 | 26.861 | 21.299 |
| 8192 | 16384 | 81.218 | 27.971 | 21.299 |
| 16384 | 32768 | 114.369 | 30.123 | 21.299 |
| 32768 | 33792 | 189.885 | 33.703 | 21.299 |

## Interpretation

The Llama run shows the same qualitative pressure as Qwen3-8B: longer actual prompt tokens increase TTFT and also push TPOT upward. This supports the claim that ContractKV's segment lifecycle problem is not purely Qwen-specific.

The run is intentionally lightweight: only two prompt sources and three measured repeats were used. It is sufficient for Phase 3 feasibility, not for final paper tables.

## Artifacts

- `configs/llama3_8b_actual_context_prompts.jsonl`
- `results/baselines/llama3_8b_actual_context_scaling_raw.csv`
- `results/baselines/llama3_8b_actual_context_scaling_summary.csv`
- `logs/phase3/llama3_8b_4096.log`
- `logs/phase3/llama3_8b_8192.log`
- `logs/phase3/llama3_8b_16384.log`
- `logs/phase3/llama3_8b_32768.log`
