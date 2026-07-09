# Phase 12B Concurrent Prefix-Cache Replay Report

## Goal

Phase 12B tests whether canonical-slot layout remains useful under concurrent replay, not just in a single-request A/B.

Compared strategies:

```text
raw-order + prefix cache
canonical-slot + prefix cache
cold raw-order + prefix cache disabled
```

Workload:

```text
Qwen3-8B
max_model_len = 8192
max_num_seqs = 2
concurrency = 1 / 2 / 4 / 6
mixed stable contexts = 5 RULER + 5 LongBench + 5 RepoBench cases
SLO buckets = 100 / 200 / 500 / 700 / 1000 ms
```

## Artifacts

```text
results/prefix_cache/phase12b_concurrent_replay_raw_v0.jsonl
results/prefix_cache/phase12b_concurrent_replay_summary_v0.csv
logs/phase12/phase12b_prefix_on_qwen3_8b.log
logs/phase12/phase12b_prefix_off_qwen3_8b_8013.log
```

## Main Result

All 180 replay requests completed.

At SLO = 700 ms:

| concurrency | raw-order mean TTFT | canonical mean TTFT | raw p95 TTFT | canonical p95 TTFT | raw SLO req/s | canonical SLO req/s |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 469.858 ms | 56.144 ms | 854.962 ms | 67.798 ms | 0.958 | 3.547 |
| 2 | 724.582 ms | 60.802 ms | 1581.111 ms | 84.426 ms | 1.025 | 6.325 |
| 4 | 1244.621 ms | 189.022 ms | 2370.169 ms | 341.416 ms | 0.466 | 6.639 |
| 6 | 1780.027 ms | 291.399 ms | 3841.783 ms | 591.771 ms | 0.348 | 6.846 |

At tighter SLOs, the distinction is sharper:

```text
SLO = 100 ms:
  canonical-slot compliant requests = 15/15 at c=1 and c=2, 8/15 at c=4, 6/15 at c=6
  raw-order compliant requests = 0/15 at all concurrency levels

SLO = 200 ms:
  canonical-slot compliant requests = 15/15 at c=1 and c=2, 8/15 at c=4, 6/15 at c=6
  raw-order compliant requests = 0/15 at all concurrency levels

SLO = 700 ms:
  canonical-slot compliant requests = 15/15 at all concurrency levels
  raw-order compliant requests = 10/15, 9/15, 4/15, 3/15 for c=1/2/4/6
```

Quality marker sanity was 1.0 for all three strategies after shortening the sanity marker to avoid max-token truncation.

## Interpretation

Canonical-slot layout turns the Phase 12A single-request TTFT reduction into an SLO goodput proxy improvement under queue pressure.

The strongest signal is at concurrency 4 and 6:

```text
c=4, SLO 700 ms:
  raw-order SLO req/s = 0.466
  canonical-slot SLO req/s = 6.639

c=6, SLO 700 ms:
  raw-order SLO req/s = 0.348
  canonical-slot SLO req/s = 6.846
```

This is a real vLLM serving-path result, not a tensor proxy.

## Boundaries

vLLM did not expose cached-token counts through the tested OpenAI streaming usage path, so this report claims TTFT and SLO-goodput proxy improvements, not measured prefix-hit tokens.

The optional canonical-slot shuffled sanity was implemented in the runner but not included in this main table. It should be used only as a follow-up artifact check, because shuffled layouts can change semantics.
