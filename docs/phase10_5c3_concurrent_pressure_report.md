# Phase 10.5C-3 Concurrent Pressure and Tier 3 SLO Report

## Goal

Upgrade the Phase 10.5C RAR-exact benchmark from repeated single-request stability to a small real concurrent pressure run.

Policies:

```text
vLLM-default
full-recompute
greedy-RAR-exact
ContractKV-RAR-exact
```

## Setup

Model and serving configuration:

```text
model = Qwen3-8B
max_model_len = 8192
max_num_seqs = 2
gpu_memory_utilization = 0.88
dtype = float16
port = 8001
```

Workload:

```text
target_words = 5000
max_tokens = 16
concurrent_requests = 2, 4, 6
SLO sweep = 2000, 2500, 3000 ms TTFT
```

Outputs:

```text
results/hard_systems/contractkv_recompute_policy_tier2_raw_v0.csv
results/hard_systems/contractkv_recompute_policy_tier2_summary_v0.csv
results/hard_systems/contractkv_recompute_policy_tier3_slo_sweep_v0.csv
```

## Tier 2 Summary at 2500 ms TTFT SLO

| Policy | Concurrency | Completed | Capacity Failures | SLO-compliant | Mean TTFT ms | P95 TTFT ms | Mean TPOT ms | Blocks Freed | Mean Headroom Gain | Saved Tokens vs Full |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| vLLM-default | 2 | 2/2 | 0 | 1 | 2746.860 | 3393.055 | 146.107 | 0 | 0.000 | 0 |
| full-recompute | 2 | 2/2 | 0 | 1 | 2695.931 | 3355.303 | 145.750 | 287 | 143.500 | 0 |
| greedy-RAR-exact | 2 | 2/2 | 0 | 1 | 3158.884 | 3821.729 | 146.368 | 127 | 63.500 | 1024 |
| ContractKV-RAR-exact | 2 | 2/2 | 0 | 0 | 3177.993 | 3783.903 | 135.202 | 95 | 47.500 | 2048 |
| vLLM-default | 4 | 4/4 | 0 | 3 | 1647.344 | 3010.966 | 135.012 | 0 | 0.000 | 0 |
| full-recompute | 4 | 4/4 | 0 | 3 | 1260.461 | 3077.091 | 109.797 | 994 | 248.500 | 0 |
| greedy-RAR-exact | 4 | 4/4 | 0 | 1 | 2996.931 | 6040.481 | 338.176 | 771 | 192.750 | 2048 |
| ContractKV-RAR-exact | 4 | 4/4 | 0 | 1 | 3310.751 | 5088.626 | 316.117 | 836 | 209.000 | 4096 |
| vLLM-default | 6 | 6/6 | 0 | 5 | 983.454 | 3194.612 | 65.013 | 0 | 0.000 | 0 |
| full-recompute | 6 | 6/6 | 0 | 5 | 1020.113 | 3288.349 | 83.519 | 1702 | 283.667 | 0 |
| greedy-RAR-exact | 6 | 6/6 | 0 | 2 | 4409.257 | 9503.250 | 409.266 | 1189 | 198.167 | 3072 |
| ContractKV-RAR-exact | 6 | 6/6 | 0 | 2 | 4108.999 | 8607.695 | 339.186 | 1125 | 187.500 | 6144 |

## Tier 3 SLO Sweep

At 2000 ms:

```text
concurrency=2: all policies 0/2 SLO-compliant
concurrency=4: default 3/4, full 3/4, greedy 1/4, ContractKV 1/4
concurrency=6: default 5/6, full 5/6, greedy 2/6, ContractKV 2/6
```

At 2500 ms:

```text
concurrency=2: default 1/2, full 1/2, greedy 1/2, ContractKV 0/2
concurrency=4: default 3/4, full 3/4, greedy 1/4, ContractKV 1/4
concurrency=6: default 5/6, full 5/6, greedy 2/6, ContractKV 2/6
```

At 3000 ms:

```text
concurrency=2: all policies 1/2 SLO-compliant
concurrency=4: default 3/4, full 3/4, greedy 3/4, ContractKV 2/4
concurrency=6: default 5/6, full 5/6, greedy 2/6, ContractKV 3/6
```

## Interpretation

This run confirms the hard-system mechanism under concurrency:

```text
ContractKV-RAR-exact completed all 12/12 requests.
ContractKV-RAR-exact triggered real vLLM suffix block release events.
ContractKV-RAR-exact saved 2048, 4096, and 6144 recompute tokens at concurrency 2, 4, and 6.
```

It does not show a goodput win yet. In this workload, vLLM-default and full-recompute have lower mean TTFT and higher SLO-compliant req/s than RAR-exact. The repeated 5000-word prompt is useful for a controlled actuator test, but it is not a strong workload for demonstrating RAR pressure benefit because repeated prompt content and server scheduling effects can make the default path unusually favorable.

## Claim Boundary

Supported:

```text
RAR-exact is stable under small Qwen3-8B concurrent pressure.
RAR-exact releases real vLLM V1 KV blocks without request failure.
ContractKV-RAR-exact reduces recompute work relative to full recompute.
```

Not supported by this run:

```text
ContractKV-RAR-exact improves SLO goodput on this repeated-prompt workload.
ContractKV-RAR-exact reduces mean or p95 TTFT in this configuration.
The benchmark reaches capacity failure pressure.
```

## Next Benchmark Correction

The next pressure run should use heterogeneous prompt content and higher actual block pressure:

```text
mixed RULER / LongBench / RepoBench prompts
disable or separate prefix-cache reuse if possible
increase pressure until default shows queueing, preemption, or capacity failure
compare RAR-exact against full recompute on recompute work and completion under pressure
```
