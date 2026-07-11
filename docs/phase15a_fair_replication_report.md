# Phase 15A Fair Fresh-Process Replication

## Protocol

Every `policy x concurrency x seed` cell ran in a fresh Qwen3-8B vLLM process with an empty prefix cache and a distinct metrics log. Three seeds used randomized policy order. Prompt-side policy and cell identifiers were removed. Each raw record includes an order-insensitive segment-content signature; it matched across raw order, static POSC, and CAPOSC for every seed and concurrency.

The natural mixed-agent replay contains 18 independent cells and 1,350 real endpoint requests. The physical fan-out replay contains 18 independent cells and 342 requests. Raw logs remain on the 8T disk; these audited CSVs are the lightweight paper records.

## Natural Mixed-Agent Results

| Concurrency | Policy | Mean TTFT | p95 TTFT | New prefill | 2 s SLO goodput |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | Raw order | 1,479 ms | 2,130 ms | 5,623 tokens | 0.261 req/s |
| 1 | Static POSC | 364 ms | 2,087 ms | 1,171 tokens | 1.188 req/s |
| 1 | CAPOSC | 363 ms | 2,086 ms | 1,171 tokens | 1.181 req/s |
| 4 | Raw order | 4,364 ms | 6,575 ms | 5,625 tokens | 0.096 req/s |
| 4 | Static POSC | 1,320 ms | 5,153 ms | 1,171 tokens | 1.486 req/s |
| 4 | CAPOSC | 1,313 ms | 4,849 ms | 1,171 tokens | 1.499 req/s |

CAPOSC reduces mean TTFT by 75.5% at concurrency one. At concurrency four it reduces p95 TTFT by 26.2% and raises 2 s SLO-compliant goodput by 15.7x. All requests completed, all server metric joins succeeded, and all marker/order sanity checks passed.

Static POSC and CAPOSC are nearly tied in this workload. This table therefore proves the real serving benefit of legal canonical layout, but does not by itself prove that cache-aware candidate selection is necessary.

## Concurrent Physical Sharing

The physical replay validates only same-scheduler-snapshot sharing. At 6K/20 sessions, static POSC and CAPOSC each reach a concurrent dedup factor of 20.0x with a refcount-match rate of 100%, while raw order has effective dedup of about 1.00x. CAPOSC lowers p95 TTFT from 30.22 s to 0.53 s and mean used-block high water from 1,513 to 446.

## Boundary

The natural replay remains a serving and marker/order-sanity experiment. Its task-quality boundary is the separate fresh task-quality calibration, not official scoring within this replay. Phase 15C must still construct a physical-cache-state conflict, and Phase 15D must still run task-bearing Certified-CAPOSC evaluation.

## Artifacts

- `results/hard_systems/phase15a_natural_fair_raw_v0.csv`
- `results/hard_systems/phase15a_natural_fair_summary_v0.csv`
- `results/hard_systems/phase15a_physical_fair_raw_v0.csv`
- `results/hard_systems/phase15a_physical_fair_summary_v0.csv`
