# Phase 15B Async Shared-Context Finite Capacity

## Protocol

This rerun supersedes the earlier synchronous-client Phase 15B report. The old
56 rps / 112x number was invalid as a finite-capacity claim because request
submission could bottleneck in the client thread pool. The fixed protocol uses
an `aiohttp` streaming client, records p95/p99 send lag, and keeps the same
three-seed stability gates: completion, minimum second-half samples, p95 TTFT
within the 5 s SLO, queue-slope, drain backlog, and all-seed agreement.

The workload is Qwen3-8B on one RTX 3090 with a 2K shared prefix. Raw order and
CAPOSC are tested on separate grids. The report keeps cold-primer cost explicit
through `mean_primer_latency_ms` and `mean_cold_start_amortized_latency_ms`.

## Result

Raw order is stable at 0.9 rps and becomes unstable at 1.0 rps. CAPOSC is stable
at 12 rps and becomes unstable at 16 rps. The measured stable-point ratio is
therefore `12 / 0.9 = 13.33x`, and the strict bracket lower bound is `>12x`
because raw already fails at 1.0 rps while CAPOSC passes 12 rps.

The send path is no longer the limiting factor: stable-point p95 send lag stays
below 4 ms, while unstable CAPOSC points fail because p95 TTFT grows to seconds
or tens of seconds. This makes the capacity knee a server-side serving result
rather than a client artifact.

| Policy | Stable rps | First unstable rps | Stable p95 TTFT | Stable SLO goodput |
| --- | ---: | ---: | ---: | ---: |
| raw-order | 0.9 | 1.0 | 3,175 ms | 0.888 req/s |
| contractkv-caposc | 12.0 | 16.0 | 399 ms | 11.983 req/s |

CAPOSC also reduces observed new-prefill work at the stable point from about
1,124 tokens/request to 15.7 tokens/request. This is the causal mechanism behind
the rate separation.

## Boundary

This is a finite-capacity open-loop replay, not a full benchmark suite. The
result should be cited as an async-client corrected lower bound: CAPOSC has at
least a 12x sustainable-rate advantage over raw order on this workload, with a
measured stable-point ratio of 13.33x.

## Artifacts

- `results/hard_systems/phase15b_async_capacity_summary_v0.csv`
- `scripts/phase14d_open_loop_capacity.py`
- `scripts/run_phase15b_shared_capacity.sh`
- `scripts/summarize_phase15b_shared_capacity.py`
