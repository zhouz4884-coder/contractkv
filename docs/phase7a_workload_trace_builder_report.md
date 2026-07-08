# Phase 7A Workload Trace Builder Report

## Goal

Build an agent-style workload trace from the 140 unified ContractKV samples.

Output:

- `results/workload/agent_trace_v0.jsonl`

## Result

The builder produced 140 trace records.

| Dataset | Traces |
| --- | ---: |
| RULER | 20 |
| LongBench | 100 |
| RepoBench | 20 |

Slack buckets:

- 0 ms: 24 traces
- 10 ms: 24 traces
- 50 ms: 23 traces
- 100 ms: 23 traces
- 200 ms: 23 traces
- 500 ms: 23 traces

Each trace includes `trace_id`, `segments`, `arrival_time_ms`, `tool_slack_ms`, `slo_ttft_ms`, and `prompt_tokens`.

## Boundary

This trace is a replay driver. It preserves the unified segment schema and metadata, but Phase 7 live replay uses compact prompt materialization to keep the serving-path experiment bounded.
