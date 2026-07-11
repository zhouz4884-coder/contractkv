# Phase 14P Natural Mixed-Agent Endpoint Replay

## Purpose

This transfer experiment tests whether cache-aware prefix ordering remains useful after the controlled shared-context probes. It uses online multi-turn sessions and the real Qwen3-8B vLLM endpoint, not a ledger latency model.

## Setup

The workload contains five agent families, three independent sessions per family, and five online turns per session. The resulting 75 requests per policy/concurrency cell are sent to a live vLLM V1 server. After each successful response, the segment-prefix ledger is updated before the next turn. The V1 metrics probe supplies observed prefix-hit and new-prefill tokens.

The compared serving policies are raw order, static POSC, and ContractKV CAPOSC. Burst concurrency is one and four. The report records OpenAI streaming timings, server-side prefix observations, compiler time, completion, and marker/order sanity.

## Results

At burst concurrency one, raw order has 1,404 ms mean TTFT and 5,396 observed new-prefill tokens. CAPOSC has 342 ms mean TTFT and 1,123 new-prefill tokens. This is a 75.6% mean-TTFT reduction. Under the 1 s SLO, CAPOSC achieves 1.169 compliant requests/s versus 0.149 for raw order, a 7.84x gain.

At burst concurrency four, CAPOSC lowers mean TTFT from 2,748 ms to 1,909 ms and p95 TTFT from 4,607 ms to 3,676 ms. The observed new-prefill work falls from 5,394 to 3,133 tokens. Under the 2 s SLO, CAPOSC achieves 0.520 compliant requests/s versus 0.175 for raw order, a 2.98x gain.

All 450 requests completed, all server-metric joins succeeded, and all marker/order checks passed. CAPOSC compiler overhead is 3.14 ms at concurrency one and 3.57 ms at concurrency four.

## Claim Boundary

This is a real endpoint-serving result with real streaming timing and V1 prefix observations. Marker/order sanity is not official task scoring. The accompanying quality claim relies on the separate fresh Phase 14R-B2 task-quality calibration; this experiment does not replace it.

## Artifacts

- `results/hard_systems/phase14p_natural_mixed_raw_v0.csv`
- `results/hard_systems/phase14p_natural_mixed_summary_v0.csv`
- `scripts/phase14d_live_mixed_serving.py`
