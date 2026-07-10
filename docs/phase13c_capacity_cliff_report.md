# Phase 13C-2 Live Capacity-Cliff Sweep

## Setup

The sweep used the live Qwen3-8B vLLM endpoint on port 8001 with prefix caching, `max_model_len=8192`, `max_num_seqs=2`, and the same 2600-word context-safe construction used by Phase 13C-1. It replayed 15 mixed RULER/LongBench/RepoBench samples at concurrency 2, 4, 6, 8, and 10 for:

```text
ContractKV-CAPOSC + SSPP
ContractKV-CAPOSC + SSPP + RAR
```

The server was restarted with a fresh RAR event log and `CONTRACTKV_ANCHOR_RECOMPUTE_MAX_EVENTS=300`.

## Artifacts

```text
results/end_to_end/phase13c_live_capacity_cliff_raw_v0.csv
results/end_to_end/phase13c_live_capacity_cliff_summary_v0.csv
results/end_to_end/phase13c_live_capacity_cliff_enriched_raw_v0.csv
results/end_to_end/phase13c_live_capacity_cliff_enriched_summary_v0.csv
results/hard_systems/phase13c_capacity_rar_events_v0.jsonl
scripts/phase13c_live_capacity_cliff.py
scripts/phase13c_capacity_analysis.py
```

## Results

All 150 live requests completed and no HTTP timeout, OOM, context-overflow, or capacity failure occurred. Mean TTFT increased from 1.29 s at concurrency 2 to 7.36 s at concurrency 10 for CAPOSC+SSPP, showing queue pressure but not a completion cliff.

At concurrency 10, RAR reduced mean TTFT from `7358.672 ms` to `7129.450 ms` and increased the 3000-ms compliant count from 2 to 3 in this run. At concurrency 4, RAR was worse (`2849.047 ms` versus `2826.735 ms`) and had fewer 3000-ms compliant requests (6 versus 9). These mixed results do not support a general goodput-improvement claim.

The fresh event log contains 150 events. All 150 request IDs join the live CSV, all have positive `free_gpu_blocks_delta`, and the aggregate observed free-block delta is 11,650. The event log has no explicit completion field; completion is established from the joined live response rows.

## Interpretation

This run proves:

1. The live endpoint can sustain the tested heterogeneous workload through concurrency 10 without capacity failure.
2. The guarded RAR actuator generated request-joinable events with positive free-GPU-block deltas.
3. Queue pressure is visible in TTFT and SLO compliance.

This run does not prove that RAR causes higher completion or SLO goodput. The actuator is enabled at the endpoint level, and its events are not an isolated causal comparison between the two policy cells. The current server configuration is also not yet at a default failure cliff.

## Decision

RAR remains a validated hard actuator with observed block release, but its live system benefit is not established. The next pressure experiment needs a calibrated capacity cliff: longer actual prompts, a lower KV budget or tighter GPU utilization, and a fresh default-versus-RAR run where the default first exhibits queueing, preemption, timeout, or capacity failure.
