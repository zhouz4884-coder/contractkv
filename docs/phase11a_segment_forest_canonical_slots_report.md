# Phase 11A Segment Forest Canonical Slots Report

## Goal

Test the next ContractKV mechanism after RAR-exact: segment-level canonicalization for stable context reuse after a dynamic middle insertion.

This phase does not claim arbitrary non-linear KV grafting. It evaluates a safer first step:

```text
Segment Radix Forest with Canonical Slots
same-slot stable segment reuse
no RoPE/position-corrected arbitrary grafting
```

## Setup

Input samples:

```text
results/datasets/sample_prompts.jsonl
num_samples = 140
RULER = 20
LongBench = 100
RepoBench = 20
```

Synthetic dynamic insertion:

```text
tool_observation_tokens = 64
raw order:       [SYS][TOOL_OBS][stable context][QUERY]
canonical order: [SYS][stable context][TOOL_OBS][QUERY]
```

Output:

```text
results/segment_fabric/segment_forest_canonical_slots_v0.csv
```

## Results

Overall:

```text
rows = 140
mean_prefill_tokens_saved = 8831.879
mean_canonical_segment_cache_hit_rate = 0.955
```

By dataset:

| Dataset | Rows | Mean Prefill Tokens Saved | Mean Canonical Hit Rate |
| --- | ---: | ---: | ---: |
| RULER | 20 | 1111.000 | 0.935 |
| RepoBench | 20 | 1113.750 | 0.925 |
| LongBench | 100 | 11919.680 | 0.965 |

By task:

| Task | Rows | Mean Prefill Tokens Saved | Mean Canonical Hit Rate |
| --- | ---: | ---: | ---: |
| hotpotqa | 20 | 14581.000 | 0.992 |
| narrativeqa | 20 | 23053.450 | 0.995 |
| qasper | 20 | 6912.750 | 0.987 |
| lcc | 20 | 3156.950 | 0.976 |
| repobench-p | 20 | 11894.250 | 0.876 |
| niah_single_1 | 20 | 1111.000 | 0.935 |
| python_repository_completion | 20 | 1113.750 | 0.925 |

## Interpretation

This is the first evidence that ContractKV can target a regime where RAR-exact is not enough:

```text
low-load repeated agent context
middle tool observation insertion
large stable context after the dynamic insertion
```

Prefix-locked caching only sees the linear prefix before the insertion. Canonical slots recover the stable context as a segment object, so the estimated prefill work falls sharply.

## Claim Boundary

Supported:

```text
Canonical slots can recover stable same-slot segment reuse opportunities that linear prefix matching misses.
The expected benefit is prefill-token reduction, not block-pressure rescue.
```

Not claimed:

```text
arbitrary KV grafting
position-corrected RoPE reuse
real vLLM prefix-cache hit improvement
real output quality after prompt re-layout
```

The next hard-system step is to run the raw-order vs canonical-order prompts on vLLM prefix caching and measure real TTFT / usage-token behavior.
