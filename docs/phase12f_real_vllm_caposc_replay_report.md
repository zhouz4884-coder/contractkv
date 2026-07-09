# Phase 12F Real vLLM CAPOSC Replay Report

## Goal

Phase 12E validated Cache-Aware POSC (CAPOSC) with a deterministic segment-ledger model. Phase 12F moves that same workload onto real vLLM serving.

The questions are:

```text
1. Does CAPOSC produce real TTFT / p95 TTFT benefit?
2. Does quality sanity remain safe?
3. Does ContractKV's estimated LCP predict real TTFT?
4. How close is CAPOSC to an oracle best-layout upper bound?
```

## Artifacts

```text
scripts/phase12f_real_vllm_caposc_replay.py
tests/test_phase12f_real_vllm_caposc.py

results/prefix_cache/phase12f_real_vllm_caposc_raw_v0.jsonl
results/prefix_cache/phase12f_real_vllm_caposc_summary_v0.csv
results/prefix_cache/phase12f_lcp_ttft_correlation_v0.csv
```

## Setup

Server:

```text
Qwen3-8B
vLLM 0.10.2
OpenAI-compatible stream API
prefix cache enabled
max_model_len = 8192
max_num_seqs = 2
port = 8016
```

Workload:

```text
2 code-agent trajectories * 6 turns
2 RAG-agent trajectories * 6 turns
2 mixed-agent trajectories * 6 turns
= 36 turns
```

Policies:

```text
raw-order
boolean-guarded
static POSC
CAPOSC
CAPOSC + rebase
oracle-best-layout
```

`oracle-best-layout` is not deployable. It is an analysis upper bound that chooses the fastest quality-safe observed policy for each turn after replay.

## Main Result

At SLO = 300 ms:

| policy | quality sanity | mean TTFT | p95 TTFT | SLO req/s | mean LCP | mean new-prefill |
|---|---:|---:|---:|---:|---:|---:|
| raw-order | 1.000000 | 128.009 ms | 265.723 ms | 2.624 | 247.056 | 276.944 |
| boolean-guarded | 1.000000 | 49.602 ms | 91.970 ms | 3.431 | 247.056 | 276.944 |
| static POSC | 1.000000 | 81.748 ms | 164.861 ms | 3.088 | 323.722 | 200.278 |
| CAPOSC | 1.000000 | 49.947 ms | 76.871 ms | 3.427 | 342.333 | 181.667 |
| CAPOSC + rebase | 1.000000 | 42.278 ms | 48.697 ms | 3.524 | 342.333 | 181.667 |
| oracle-best-layout | 1.000000 | 41.137 ms | 46.890 ms | 3.538 | 303.278 | 220.722 |

Relative to boolean-guarded:

```text
CAPOSC:
  mean TTFT = essentially tied (-0.7% slower)
  p95 TTFT = 16.4% lower

CAPOSC + rebase:
  mean TTFT = 14.8% lower
  p95 TTFT = 47.1% lower
  SLO req/s = 2.7% higher
```

Relative to static POSC:

```text
CAPOSC mean TTFT reduction = 38.9%
CAPOSC p95 TTFT reduction = 53.4%
```

This directly confirms the Phase 12E hypothesis:

```text
static POSC can break de facto cached prefix state;
CAPOSC recovers that state and avoids static POSC's tail latency failure.
```

## Case-Type Breakdown

### Code-Agent

| policy | mean TTFT | p95 TTFT | quality |
|---|---:|---:|---:|
| raw-order | 227.307 ms | 269.186 ms | 12/12 |
| boolean-guarded | 45.649 ms | 49.427 ms | 12/12 |
| static POSC | 118.899 ms | 191.132 ms | 12/12 |
| CAPOSC | 44.128 ms | 46.811 ms | 12/12 |
| CAPOSC + rebase | 45.219 ms | 47.170 ms | 12/12 |
| oracle-best-layout | 43.256 ms | 45.944 ms | 12/12 |

CAPOSC is closest to oracle on code-agent trajectories. This is the clearest win for cache-aware partial-order layout.

### Mixed-Agent

| policy | mean TTFT | p95 TTFT | quality |
|---|---:|---:|---:|
| raw-order | 72.306 ms | 153.261 ms | 12/12 |
| boolean-guarded | 40.731 ms | 45.825 ms | 12/12 |
| static POSC | 85.014 ms | 152.939 ms | 12/12 |
| CAPOSC | 53.351 ms | 71.707 ms | 12/12 |
| CAPOSC + rebase | 40.371 ms | 45.948 ms | 12/12 |
| oracle-best-layout | 39.568 ms | 44.469 ms | 12/12 |

This is the main rebase case. Plain CAPOSC is safe but slower than boolean; CAPOSC + rebase recovers almost all oracle benefit.

### RAG-Agent

| policy | mean TTFT | p95 TTFT | quality |
|---|---:|---:|---:|
| raw-order | 84.415 ms | 134.869 ms | 12/12 |
| boolean-guarded | 62.427 ms | 112.781 ms | 12/12 |
| static POSC | 41.331 ms | 48.951 ms | 12/12 |
| CAPOSC | 52.363 ms | 81.603 ms | 12/12 |
| CAPOSC + rebase | 41.244 ms | 48.854 ms | 12/12 |
| oracle-best-layout | 40.587 ms | 48.854 ms | 12/12 |

For RAG-agent, static POSC is already close to optimal, and CAPOSC + rebase matches it.

## Quality Sanity

All real policy requests completed:

```text
error_type none = 180 / 180
quality_bad = 0 / 180
```

Quality sanity checks:

```text
violated_edges = 0
expected marker present
ORDER_ERROR absent
```

This addresses the core Phase 12C concern: CAPOSC changes layout while preserving the POSC dependency contract.

## LCP vs Real TTFT Calibration

vLLM did not expose cached-token counts through the tested OpenAI stream usage fields:

```text
cached_tokens_observable_rate = 0.0
```

Therefore, Phase 12F uses real TTFT correlation as an indirect calibration of the Segment Prefix Ledger.

Global correlation over non-oracle real requests:

```text
estimated_lcp_tokens vs real_TTFT:
  Pearson r = -0.304888
  Spearman r = -0.052310

estimated_new_prefill_tokens vs real_TTFT:
  Pearson r = 0.390593
  Spearman r = 0.402107
```

Per-policy strongest signals:

```text
raw-order:
  estimated_new_prefill_tokens vs real_TTFT Pearson r = 0.593930
  Spearman r = 0.964257

static POSC:
  estimated_new_prefill_tokens vs real_TTFT Pearson r = 0.782082
  Spearman r = 0.687896
```

CAPOSC's per-policy correlation is weaker and sometimes inverted, because the selector deliberately switches among candidates. This means:

```text
the ledger is predictive of real TTFT pressure in fixed-layout regimes;
for adaptive policies, candidate-switching and scheduler/cache noise must be modeled explicitly.
```

## Oracle Gap

CAPOSC + rebase is close to oracle:

```text
oracle mean TTFT = 41.137 ms
CAPOSC + rebase mean TTFT = 42.278 ms
gap = 1.141 ms

oracle p95 TTFT = 46.890 ms
CAPOSC + rebase p95 TTFT = 48.697 ms
gap = 1.807 ms
```

This suggests the CAPOSC scoring function is already near the best observed layout on this workload.

## What This Proves

Phase 12F proves:

```text
1. CAPOSC reaches real vLLM serving path.
2. CAPOSC preserves output sanity on 180 real streamed requests.
3. CAPOSC reduces p95 TTFT versus boolean-guarded.
4. CAPOSC + rebase improves both mean and p95 TTFT and approaches oracle-best.
5. ContractKV's estimated new-prefill tokens correlate positively with real TTFT at the workload level.
```

## What This Does Not Prove

Phase 12F still does not claim:

```text
direct observed vLLM cached-token hit rate
production throughput
arbitrary non-linear KV grafting
RoPE-corrected segment stitching
real KV block movement for CAPOSC
```

The right claim is:

```text
CAPOSC is a real vLLM prompt-layout compiler that uses segment contracts and cache-state estimates to reduce real TTFT tail latency while preserving quality sanity.
```

## Decision

Phase 12F closes the main gap left by Phase 12E.

Recommended next step:

```text
Phase 12G: concurrent CAPOSC replay
  concurrency = 1 / 2 / 4
  compare boolean-guarded, CAPOSC, CAPOSC + rebase, oracle-best
  report SLO-compliant req/s and p95 TTFT under queue pressure
```

After that, CAPOSC can be integrated into the broader ContractKV story as the low/normal-load serving benefit, while RAR-exact remains the high-pressure block-residency actuator.
