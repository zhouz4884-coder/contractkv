# Phase 15B Shared-Context Finite Capacity

## Protocol

This is an open-loop Poisson replay over a 2K shared prefix with Qwen3-8B and one RTX 3090. All points use a 5 s TTFT SLO. A stable point requires all of: at least 200 completed requests, at least 100 second-half samples, completion at least 99%, p95 TTFT within the SLO, queue-wait slope at most 0.02 seconds per second, and zero drain backlog. A capacity point is reportable only if all three independent seeds pass.

The report records both steady-state capacity and cold-start amortized latency. CAPOSC primer latency is therefore explicit rather than excluded from the analysis.

## Result

Raw order at 0.5 req/s passes all three seeds, with at least 240 completions per seed and maximum p95 TTFT of 1.53 s. Raw order at 1 req/s does not pass all seeds: its worst p95 reaches 12.33 s and its wait slope reaches 0.139.

CAPOSC at 56 req/s passes all three seeds, with at least 809 completions per seed, zero backlog, maximum p95 TTFT of 2.44 s, and maximum queue slope of 0.00095. Its mean observed new-prefill work is 22.3 tokens/request versus 1,271.9 for raw order at the stable raw point.

Thus the measured grid establishes a conservative 112x sustainable-rate lower bound, `56 / 0.5`. It is a lower bound, not an exact CAPOSC knee: 72 req/s was not completed for all three seeds, and higher rates were not searched. The 5 s protocol intentionally separates finite capacity from the stronger but different 2 s SLO-feasibility separation.

## Artifacts

- `results/hard_systems/phase15b_shared_capacity_summary_v0.csv`
- `scripts/phase14d_open_loop_capacity.py`
- `scripts/run_phase15b_shared_capacity.sh`
