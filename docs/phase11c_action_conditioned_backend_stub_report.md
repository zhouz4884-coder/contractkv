# Phase 11C Action-Conditioned Backend Stub Report

## Goal

Evaluate whether ContractKV's control plane can select quant/offload backend actions more safely than uniform backend use.

This phase is intentionally a backend stub:

```text
no real KIVI kernel
no real LMCache/Tutti integration
no mixed-precision attention kernel
```

The question is attribution:

```text
same backend primitive
uniform policy vs ContractKV segment-aware policy
```

## Setup

Inputs:

```text
results/datasets/sample_prompts.jsonl
results/hard_systems/real_quality_risk_summary_qwen3_8b_v0.csv
```

Policies:

```text
vllm-fp16
uniform-int4
contractkv-int4
uniform-offload
contractkv-offload
```

Quality budget:

```text
epsilon = 0.03
```

Output:

```text
results/segment_fabric/action_conditioned_backend_stub_v0.csv
```

## Results

| Policy | Rows | Quality Violations | Mean Memory Saving MB | Mean Quality Risk | Mean Residual Stall ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| vllm-fp16 | 140 | 0 | 0.000 | 0.0000 | 0.000 |
| uniform-int4 | 140 | 140 | 107.952 | 0.0800 | 0.000 |
| contractkv-int4 | 140 | 0 | 25.802 | 0.0005 | 0.000 |
| uniform-offload | 140 | 0 | 143.935 | 0.0000 | 11.713 |
| contractkv-offload | 140 | 0 | 141.310 | 0.0000 | 0.000 |

ContractKV-int4 by task:

| Dataset / Task | Mean Memory Saving MB | Mean Quality Risk | Quantized Rows |
| --- | ---: | ---: | ---: |
| LongBench / lcc | 37.883 | 0.0000 | 20 |
| LongBench / repobench-p | 142.731 | 0.0036 | 20 |
| LongBench / hotpotqa | 0.000 | 0.0000 | 0 |
| LongBench / narrativeqa | 0.000 | 0.0000 | 0 |
| LongBench / qasper | 0.000 | 0.0000 | 0 |
| RULER / niah_single_1 | 0.000 | 0.0000 | 0 |
| RepoBench / python_repository_completion | 0.000 | 0.0000 | 0 |

## Interpretation

Uniform INT4 saves more memory but violates the quality budget for every row under this conservative risk model.

ContractKV-int4 saves less memory, but it remains inside the quality budget by only unlocking tasks whose real Phase 10.2B segment-eviction risk is already below the budget. This is the intended fail-closed behavior:

```text
do not compress high-risk context just because a backend exists
only unlock backend actions when the segment/task contract allows it
```

ContractKV-offload retains almost the same memory saving as uniform offload in this stub, but uses 100 ms slack to hide transfer residual stall.

## Claim Boundary

Supported:

```text
Action-conditioned risk separates backend choice from backend capability.
ContractKV can use the same INT4/offload primitive more selectively than uniform policies.
```

Not claimed:

```text
real quantized KV attention quality
real host/SSD offload throughput
real mixed-precision softmax merge
```

The next step is to replace the INT4/offload stubs with one real backend primitive at a time while keeping the same policy comparison.
