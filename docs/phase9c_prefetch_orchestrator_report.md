# Phase 9C Prefetch Orchestrator Proxy Report

## Goal

Move the Phase 8 tool-slack transfer proxy closer to the request lifecycle:

```text
ContractKV decision plan -> predicted transfer size -> tool_slack_ms -> copy_now/defer/skip -> residual stall log
```

## Method

Script:

```text
scripts/vllm_prefetch_orchestrator_proxy.py
```

Inputs:

```text
results/workload/agent_trace_v0.jsonl
results/runtime/tool_slack_copy_proxy_v0.csv
```

Output:

```text
results/runtime/vllm_prefetch_orchestrator_proxy_v0.csv
```

The proxy predicts transfer size from the largest segment token count:

```text
<500 tokens   -> 128 MB
>=500 tokens  -> 256 MB
>=1000 tokens -> 512 MB
>=4000 tokens -> 1024 MB
```

Policy behavior:

```text
No-Contract       -> skip
ContractKV-Indep  -> copy_now
ContractKV-Joint  -> choose copy_now/defer_to_slack/skip from slack and size
```

## Result

The orchestrator produced:

```text
420 rows
```

Strategy distribution:

```text
No-Contract:       skip=140
ContractKV-Indep:  copy_now=140
ContractKV-Joint:  copy_now=49, defer_to_slack=79, skip=12
```

Mean residual stall:

```text
No-Contract:       0.000 ms
ContractKV-Indep:  60.062 ms
ContractKV-Joint:  20.916 ms
```

This reproduces the Phase 8 slack boundary: slack-window scheduling hides a substantial part of the transfer cost, while large transfers with insufficient slack are skipped rather than forced onto the critical path.

## Boundary

The proxy does not move real vLLM KV cache. It is still a request-adjacent transfer proxy.
