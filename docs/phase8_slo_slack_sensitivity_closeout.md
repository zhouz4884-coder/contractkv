# Phase 8 SLO and Tool-Slack Sensitivity Closeout

## Why Phase 8

Phase 7 showed that ContractKV-Joint can run a live vLLM workload replay while preserving quality constraints, but the 200 ms TTFT SLO was intentionally tight. Phase 8 expands the boundary analysis before moving toward vLLM hooks.

## Inputs from Phase 7

- `results/workload/live_replay_raw_v0.csv`
- `results/runtime/tool_slack_copy_proxy_v0.csv`
- Policies: No-Contract, ContractKV-Indep, ContractKV-Joint
- Dataset traces: RULER, LongBench, RepoBench

## SLO Sensitivity Results

Joint has quality violation 0.0 at all SLO buckets. Indep has quality violation 1.0 at all SLO buckets, so it remains inadmissible even when SLO is relaxed.

Joint's SLO-compliant goodput increases as SLO is relaxed:

- 200 ms: 1.943 req/s
- 300 ms: 15.667 req/s
- 500 ms and above: 16.230 req/s

This shows that 200 ms was a strong stress point and that 300-500 ms is the more informative transition range for the current prototype.

## Tool-Slack Sensitivity Results

Short slack can hide small transfers, but large transfers need larger slack:

- 128 MB: almost hidden at 10 ms, fully hidden at 50 ms
- 256 MB: fully hidden at 50 ms
- 512 MB: fully hidden at 50 ms
- 1024 MB: still leaves 31.340 ms residual stall at 50 ms, fully hidden at 100 ms

## What This Proves

ContractKV-Joint is robust to SLO relaxation while preserving the quality budget. Indep fails for quality reasons, not only latency reasons. Slack-aware transfer scheduling materially changes residual stall and therefore TTFT pressure.

## What It Still Does Not Prove

Phase 8 still does not claim real KV placement, true KV cache memory saving, or production serving throughput. It is an offline sensitivity sweep over Phase 7 live replay and Phase 6C transfer proxy measurements.

## Decision for Phase 9

Proceed to a vLLM-adjacent Python metadata hook rather than CUDA/kernel work. The next phase should preserve request_id, segment plan, risk, and placement decisions near the vLLM request path, then add read-only block/prefix stats observation.
