# Phase 12A Real vLLM Prefix-Cache A/B Report

## Goal

Validate whether ContractKV canonical-slot layout can turn Phase 11A's control-plane estimate into a real vLLM serving benefit.

This phase tests only:

```text
canonical slot layout + real vLLM prefix-cache A/B
```

It does not claim arbitrary non-linear KV grafting, MiniPIC-style position correction, or RoPE-corrected stitching.

## Setup

Model and server:

```text
model = Qwen3-8B
vLLM = 0.10.2
max_model_len = 8192
max_num_seqs = 2
dtype = float16
gpu_memory_utilization = 0.88
```

Prompt structure:

```text
Turn 1:
[SYS][STABLE_CONTEXT][QUERY_1]

Turn 2 raw-order:
[SYS][TOOL_OBS_dynamic][STABLE_CONTEXT][QUERY_2]

Turn 2 canonical-slot:
[SYS][STABLE_CONTEXT][TOOL_OBS_dynamic][QUERY_2]
```

Baseline:

```text
cold-raw with --no-enable-prefix-caching
```

Each layout uses:

```text
repeats = 5
stable_words = 2500
prompt_tokens ~= 2536
max_tokens = 16
temperature = 0
```

Outputs:

```text
results/prefix_cache/phase12_prefix_cache_ab_raw_v0.jsonl
results/prefix_cache/phase12_prefix_cache_ab_summary_v0.csv
results/prefix_cache/phase12_vllm_prefix_cache_log_notes.txt
```

## Server Evidence

The server logs record the actual prefix-cache settings:

```text
prefix-on:  extra_vllm_args=--enable-prefix-caching
prefix-on:  enable_prefix_caching=True
prefix-off: extra_vllm_args=--no-enable-prefix-caching
prefix-off: enable_prefix_caching=False
```

The OpenAI streaming response did not expose cached-token usage fields, so this report does not claim a numeric cached-token hit rate.

## Results

| Layout | Prefix Cache | Requests | Quality Sanity | Mean TTFT ms | P95 TTFT ms | Mean TPOT ms | Mean Latency ms | TTFT Reduction vs Raw | P95 Reduction vs Raw |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| raw-order | on | 5 | 1.0 | 638.457 | 640.707 | 21.967 | 880.999 | 0.000% | 0.000% |
| canonical-slot | on | 5 | 1.0 | 58.590 | 64.610 | 21.885 | 300.884 | 90.823% | 89.916% |
| cold-raw | off | 5 | 1.0 | 736.005 | 1051.352 | 21.847 | 977.238 | -15.279% | -64.092% |

All outputs contained the expected marker:

```text
PHASE12_MARKER_<repeat_id>
```

## Success Standard

Minimum success:

```text
canonical-slot TTFT < raw-order TTFT
quality sanity does not drop
```

Met.

Strong success:

```text
canonical-slot mean TTFT reduction >= 10%
or canonical-slot p95 TTFT reduction >= 10%
```

Met:

```text
mean TTFT reduction = 90.823%
p95 TTFT reduction = 89.916%
```

Top-tier success:

```text
SLO-compliant req/s improves
and cached-token / prefix-cache reuse behavior is directly observable
```

Not fully met in this phase. TTFT improved strongly, but cached-token counts were not exposed by the OpenAI streaming API.

## Interpretation

This is the first hard evidence that ContractKV is not only a high-pressure RAR mechanism.

The result supports a low-load / normal-load benefit:

```text
middle dynamic ToolObs insertion breaks linear prefix reuse
canonical-slot layout keeps stable context in the reusable prefix region
real vLLM TTFT falls sharply
output sanity remains intact
```

The cold no-prefix baseline is slower than raw-order with prefix cache, which confirms prefix caching is active and beneficial even for raw-order. Canonical-slot is much faster because it preserves a much longer useful prefix between Turn 1 and Turn 2.

## Claim Boundary

Supported:

```text
Canonical-slot prompt layout improves real Qwen3-8B vLLM TTFT under prefix caching for this controlled repeated-context workload.
The improvement is observed in real OpenAI-compatible streaming TTFT, not a proxy timer.
Output marker sanity is preserved.
```

Not claimed:

```text
arbitrary non-linear KV grafting
position-corrected KV reuse
real segment-level block-table grafting
numeric cached-token hit rate
general production goodput improvement
```

## Next

Phase 12B should run a small concurrent replay:

```text
raw-order vs canonical-slot
prefix cache enabled
concurrency = 1 / 2 / 4
mixed stable contexts from RepoBench and LongBench
metrics: SLO-compliant req/s, mean/p95 TTFT, quality sanity
```
