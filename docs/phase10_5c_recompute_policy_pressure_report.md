# Phase 10.5C Recompute Policy Pressure Report

## Goal

Evaluate RAR-exact before adding KIVI, LMCache-style offload, or any compressed KV backend.

Policies:

```text
vLLM-default
full-recompute
greedy-RAR-exact
ContractKV-RAR-exact
```

## Setup

Model:

```text
Qwen3-8B
max_model_len = 8192
max_num_seqs = 2
gpu_memory_utilization = 0.88
```

Probe:

```text
single long streaming request
target_words = 5000
max_tokens = 16
SLO TTFT = 200 ms
```

This is a `tier0_debug` hard-system probe, not the final high-concurrency pressure benchmark.

## Outputs

```text
results/hard_systems/contractkv_recompute_policy_events_v0.csv
results/hard_systems/contractkv_recompute_policy_eval_v0.csv
```

## Results

| Policy | Completed | Capacity Failures | SLO-compliant req/s | Mean TTFT ms | Mean TPOT ms | Blocks Freed | Recompute Tokens Saved vs Full |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| vLLM-default | 1 | 0 | 0.0 | 1938.703 | 23.017 | 0 | 0 |
| full-recompute | 1 | 0 | 0.0 | 1944.164 | 23.144 | 128 | 0 |
| greedy-RAR-exact | 1 | 0 | 0.0 | 2286.198 | 23.126 | 96 | 512 |
| ContractKV-RAR-exact | 1 | 0 | 0.0 | 2179.320 | 23.121 | 64 | 1024 |

## Interpretation

The main hard-system signal is not SLO goodput yet. With a 200 ms TTFT SLO, all single long-prompt runs violate SLO.

The useful tier0 findings are:

```text
full-recompute releases the whole request block table: 128 blocks
greedy-RAR-exact releases suffix blocks from anchor=512: 96 blocks
ContractKV-RAR-exact releases suffix blocks from anchor=1024: 64 blocks
ContractKV-RAR-exact saves 1024 recompute tokens vs full recompute
```

This supports the architectural claim that RAR-exact can trade block headroom against recompute work without deleting prompt text.

## Boundary

This report does not claim throughput improvement. It establishes that the four-policy measurement path is wired to real vLLM V1 actuator events and stream timing. The next run should increase `num_requests` and concurrency to measure `completion_lift_vs_default` and `SLO_goodput_delta_vs_default` under real block pressure.
