# Phase 6B Controller Overhead Report

## Goal

Measure Python-side ContractKV controller overhead for segment parsing, policy decision, JSON logging, and end-to-end proxy bookkeeping.

## Inputs

- RULER: 20 samples
- LongBench: 20 samples
- RepoBench: 20 samples
- Models represented: Qwen3-4B and Qwen3-8B

Output:

- `results/runtime/controller_overhead_v0.csv`

## Results

Rows: 120.

| Metric | Value |
| --- | ---: |
| Mean policy time | 0.090 ms |
| P95 policy time | 0.132 ms |
| Max proxy overhead ratio | 0.0135 |

By model:

| Model | Rows | Mean policy ms | Max overhead ratio |
| --- | ---: | ---: | ---: |
| Qwen3-4B | 60 | 0.094 | 0.0149 |
| Qwen3-8B | 60 | 0.092 | 0.0094 |

The target `policy_ms < 5 ms` is satisfied with a large margin.

## Timing Source

The controller overhead is measured directly in Python. `vllm_ttft_ms` in this table is a Phase 2 reference timing model used to compute overhead ratio for replay-scale samples. Live vLLM forwarding is separately validated in Phase 6A.
