# Phase 12G Concurrent CAPOSC Replay Report

## Goal

Phase 12F showed that CAPOSC improves real vLLM single-stream tail latency. Phase 12G asks whether the benefit survives concurrent replay:

```text
concurrency = 1 / 2 / 4
model = Qwen3-8B
vLLM prefix cache enabled
max_num_seqs = 2
```

The main metric is:

```text
SLO-compliant req/s = compliant requests / measured policy wall-clock replay time
```

## Artifacts

```text
scripts/phase12g_concurrent_caposc_replay.py
tests/test_phase12g_concurrent_caposc.py

results/prefix_cache/phase12g_concurrent_caposc_raw_v0.jsonl
results/prefix_cache/phase12g_concurrent_caposc_summary_v0.csv
```

## Method

Policies:

```text
boolean-guarded
static POSC
CAPOSC
CAPOSC + rebase
oracle-best-layout
```

The replay uses the same 36-turn Phase 12E/12F trajectory set. Each measured policy replay is preceded by an unrecorded warmup pass so cross-policy comparisons do not mainly reflect cold-prefix ordering.

Total recorded rows:

```text
432 real deployed-policy requests
108 oracle-best analysis rows
540 total raw rows
```

All deployed requests completed:

```text
error_type none = 432 / 432
quality_bad = 0 / 432
```

## Main Results

At SLO = 300 ms:

| concurrency | policy | mean TTFT | p95 TTFT | SLO req/s | quality |
|---:|---|---:|---:|---:|---:|
| 1 | boolean-guarded | 43.099 ms | 49.300 ms | 3.510 | 1.000 |
| 1 | static POSC | 43.042 ms | 49.419 ms | 3.507 | 1.000 |
| 1 | CAPOSC | 42.899 ms | 50.100 ms | 3.509 | 1.000 |
| 1 | CAPOSC + rebase | 42.506 ms | 48.283 ms | 3.516 | 1.000 |
| 1 | oracle-best-layout | 41.104 ms | 45.704 ms | 3.507 | 1.000 |
| 2 | boolean-guarded | 47.859 ms | 51.560 ms | 6.785 | 1.000 |
| 2 | static POSC | 47.784 ms | 51.802 ms | 6.781 | 1.000 |
| 2 | CAPOSC | 48.490 ms | 55.006 ms | 6.764 | 1.000 |
| 2 | CAPOSC + rebase | 46.113 ms | 51.285 ms | 6.826 | 1.000 |
| 2 | oracle-best-layout | 45.037 ms | 48.979 ms | 6.826 | 1.000 |
| 4 | boolean-guarded | 287.271 ms | 319.221 ms | 4.445 | 1.000 |
| 4 | static POSC | 286.479 ms | 323.204 ms | 4.832 | 1.000 |
| 4 | CAPOSC | 286.462 ms | 320.962 ms | 4.864 | 1.000 |
| 4 | CAPOSC + rebase | 287.670 ms | 325.132 ms | 4.849 | 1.000 |
| 4 | oracle-best-layout | 275.564 ms | 313.029 ms | 5.034 | 1.000 |

## Relative To Boolean-Guarded

At concurrency 1:

```text
CAPOSC + rebase:
  mean TTFT reduction = 1.38%
  p95 TTFT reduction = 2.06%
  SLO req/s improvement = 0.17%
```

At concurrency 2:

```text
CAPOSC + rebase:
  mean TTFT reduction = 3.65%
  p95 TTFT reduction = 0.53%
  SLO req/s improvement = 0.61%
```

At concurrency 4:

```text
CAPOSC:
  mean TTFT reduction = 0.28%
  p95 TTFT change = -0.55%
  SLO req/s improvement = 9.41%

CAPOSC + rebase:
  mean TTFT change = -0.14%
  p95 TTFT change = -1.85%
  SLO req/s improvement = 9.08%
```

Concurrency 4 is the queue-pressure regime because server `max_num_seqs = 2` while the client issues 4 concurrent requests. Here CAPOSC does not uniformly lower p95, but it improves SLO-compliant throughput around the 300 ms boundary.

## Interpretation

Phase 12G gives a more nuanced result than Phase 12F:

```text
low/moderate concurrency:
  CAPOSC + rebase is consistently best or near-oracle.

queue pressure:
  all policies converge toward scheduler-dominated TTFT,
  but CAPOSC/CAPOSC+rebase improve SLO-compliant req/s versus boolean.
```

The selected-policy mix for CAPOSC was stable across all concurrencies:

```text
cache-aware-posc: 26 / 36
static POSC: 8 / 36
boolean-guarded fallback: 2 / 36
```

This is important because CAPOSC is not just a boolean guard. It is a state-aware selector that still falls back when the cached raw/boolean layout is better.

## What This Proves

Phase 12G proves:

```text
1. CAPOSC can run under concurrent real vLLM replay.
2. Quality sanity remains intact under concurrency.
3. CAPOSC + rebase remains near oracle at concurrency 1/2.
4. Under queue pressure, CAPOSC improves SLO-compliant req/s even when p95 is scheduler dominated.
```

## Boundaries

Phase 12G still does not claim:

```text
production throughput
direct vLLM cached-token hit-rate observation
real KV block movement
arbitrary non-linear KV stitching
```

The OpenAI stream path still does not expose cached-token counts, so prefix-cache behavior is inferred from real timing rather than direct cached-token metrics.

## Decision

Phase 12F and 12G together establish the low/normal-load CAPOSC story:

```text
Phase 12F:
  CAPOSC improves real single-stream p95 TTFT.

Phase 12G:
  CAPOSC survives concurrent replay and improves SLO-compliant req/s under queue pressure.
```

Recommended next step:

```text
Phase 13:
  larger agent-trace replay
  more realistic arrival processes
  separate cache warmup, cache eviction, and scheduler saturation effects
```
