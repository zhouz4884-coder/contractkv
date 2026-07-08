# Phase 10.5 Tier 2 and Tier 3 Total Result

## What Was Completed

This batch completed:

```text
Tier 2: Qwen3-8B concurrent pressure for 4 policies at concurrency 2 / 4 / 6
Tier 3: TTFT SLO sweep at 2000 / 2500 / 3000 ms
```

New result files:

```text
results/hard_systems/contractkv_recompute_policy_tier2_raw_v0.csv
results/hard_systems/contractkv_recompute_policy_tier2_summary_v0.csv
results/hard_systems/contractkv_recompute_policy_tier3_slo_sweep_v0.csv
```

New report:

```text
docs/phase10_5c3_concurrent_pressure_report.md
```

## Main Result

The strongest positive result is mechanism stability:

```text
all policies completed all 12/12 concurrent requests
ContractKV-RAR-exact freed real suffix KV blocks in vLLM V1
ContractKV-RAR-exact saved 12288 total recompute tokens vs full recompute across Tier 2
```

The strongest negative result is that this workload does not show goodput improvement:

```text
capacity_failures = 0 for all policies
completion_lift_vs_default = 0 for all RAR rows
SLO_goodput_delta_vs_default is negative for ContractKV-RAR-exact at all tested concurrency levels
```

## Key Numbers

At 2500 ms TTFT SLO:

| Concurrency | Default SLO-compliant | ContractKV SLO-compliant | ContractKV Blocks Freed | ContractKV Saved Tokens vs Full |
| ---: | ---: | ---: | ---: | ---: |
| 2 | 1/2 | 0/2 | 95 | 2048 |
| 4 | 3/4 | 1/4 | 836 | 4096 |
| 6 | 5/6 | 2/6 | 1125 | 6144 |

At 3000 ms TTFT SLO:

| Concurrency | Default SLO-compliant | ContractKV SLO-compliant |
| ---: | ---: | ---: |
| 2 | 1/2 | 1/2 |
| 4 | 3/4 | 2/4 |
| 6 | 5/6 | 3/6 |

## Data Conclusion

This batch proves that ContractKV-RAR-exact is a real vLLM actuator path, not a tensor proxy:

```text
it changes real vLLM block residency
it preserves request completion
it saves exact recompute work relative to full recompute
```

But it does not yet prove system throughput benefit. The right conclusion is:

```text
ContractKV has crossed into hard-system actuation, but the current repeated-prompt Tier 2 benchmark is not the workload where RAR-exact wins on SLO goodput.
```

## Decision

Do not add KIVI/offload yet. First fix the pressure benchmark:

```text
use heterogeneous real prompts from the 140 unified samples
avoid repeated prompt reuse effects
push pressure until default shows queueing, natural preemption, or capacity failure
then re-evaluate completion_lift, capacity_failure_reduction, and SLO_goodput_delta
```
