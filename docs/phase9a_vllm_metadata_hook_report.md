# Phase 9A vLLM Metadata Hook Report

## Goal

Move ContractKV from an external trace/proxy record into a vLLM-adjacent request metadata object. The object is keyed by the same request id used by the OpenAI-compatible serving-path replay.

## Method

Script:

```text
scripts/vllm_metadata_hook_proxy.py
```

Input:

```text
results/workload/agent_trace_v0.jsonl
```

Output:

```text
results/runtime/vllm_metadata_hook_logs_v0.jsonl
```

The script builds one metadata record per `(policy, trace)` pair for:

```text
No-Contract
ContractKV-Indep
ContractKV-Joint
```

Each record carries:

```text
request_id
trace_id
segment_list
segment_token_counts
risk_budget
slo_budget_ms
tool_slack_ms
estimated_risk
admitted
decision_plan
controller_timings_ms
```

The OpenAI response format is explicitly marked as unchanged.

## Result

The metadata hook produced:

```text
420 metadata records
140 unique traces
420 unique request ids
```

This satisfies the Phase 9A requirement that all 140 workload traces can generate metadata logs and that each metadata record can align with a vLLM request id.

## Boundary

This is a request metadata sidecar. It does not modify vLLM internals and does not move real KV cache blocks.
