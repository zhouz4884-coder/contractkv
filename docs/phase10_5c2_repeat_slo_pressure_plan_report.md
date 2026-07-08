# Phase 10.5C-2 Repeat and SLO Pressure Plan Report

## Goal

Upgrade Phase 10.5C from a one-shot `tier0_debug` probe into a stable benchmark sequence before adding KIVI, offload, or compression.

This report covers Tier 1 and prepares Tier 2/3:

```text
Tier 1: repeated single-request stability
Tier 2: concurrent pressure benchmark
Tier 3: SLO sweep with meaningful TTFT budgets
```

## Tier 1 Setup

Model:

```text
Qwen3-8B
max_model_len = 8192
max_num_seqs = 2
target_words = 5000
max_tokens = 16
repeats = 10
```

Policies:

```text
vLLM-default
full-recompute
greedy-RAR-exact
ContractKV-RAR-exact
```

Outputs:

```text
results/hard_systems/contractkv_recompute_policy_repeat_raw_v0.csv
results/hard_systems/contractkv_recompute_policy_repeat_summary_v0.csv
results/hard_systems/contractkv_recompute_policy_slo_sweep_v0.csv
results/hard_systems/contractkv_recompute_policy_repeat_quality_eval_v0.csv
```

## Tier 1 Results

| Policy | Success Rate | Mean TTFT ms | P95 TTFT ms | Mean TPOT ms | Blocks Freed | Mean Headroom Gain | Saved Tokens vs Full |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| vLLM-default | 10/10 | 1484.496 | 1999.504 | 22.847 | 0 | 0 | 0 |
| full-recompute | 10/10 | 1470.952 | 1937.759 | 22.778 | 1280 | 128 | 0 |
| greedy-RAR-exact | 10/10 | 1824.470 | 2297.352 | 22.760 | 960 | 96 | 5120 |
| ContractKV-RAR-exact | 10/10 | 1711.137 | 2180.281 | 22.939 | 640 | 64 | 10240 |

Mechanism signal:

```text
full-recompute releases 128 blocks per request
greedy-RAR-exact releases 96 blocks per request
ContractKV-RAR-exact releases 64 blocks per request
ContractKV-RAR-exact saves 1024 recompute tokens per request vs full recompute
```

Quality sanity:

```text
all four policies: 10/10 successful outputs
all four policies: quality_drop = 0.0 on the OK probe
```

## Tier 3 SLO Sweep

The original 200 ms SLO is not meaningful for a 5000-word Qwen3-8B prompt. Tier 1 therefore evaluates:

```text
SLO = 2000 ms
SLO = 2500 ms
SLO = 3000 ms
```

At 2000 ms:

```text
vLLM-default: 10/10 SLO-compliant
full-recompute: 10/10 SLO-compliant
greedy-RAR-exact: 9/10 SLO-compliant
ContractKV-RAR-exact: 9/10 SLO-compliant
```

At 2500 ms and 3000 ms, all four policies are 10/10 SLO-compliant.

## Interpretation

Tier 1 confirms the mechanism is stable:

```text
ContractKV-RAR-exact consistently frees real vLLM suffix blocks
ContractKV-RAR-exact consistently saves recompute tokens vs full recompute
ContractKV-RAR-exact preserves output quality on the repeat probe
```

It does not yet prove throughput or goodput improvement because this is still sequential single-request replay.

## Tier 2 Next

The next required experiment is real concurrent pressure:

```text
Qwen3-8B:
  max_model_len = 8192
  max_num_seqs = 2 / 4 if launchable
  concurrent_requests = 2 / 4 / 6

Qwen3-4B:
  max_model_len = 8192 or 16384
  max_num_seqs = 8 / 12 / 16
  concurrent_requests = 8 / 16 / 24
```

Tier 2 success should be judged by:

```text
completed_requests
capacity_failures
natural_preemptions
forced_recompute_events
mean_block_headroom_gain
total_blocks_freed
recompute_tokens_saved_vs_full
SLO-compliant req/s
mean / p95 TTFT
```

The key target is not lower average TTFT. The key target is pressure robustness:

```text
complete more requests
reduce capacity failures
improve SLO-compliant req/s under meaningful SLO
reduce full recompute work
```
