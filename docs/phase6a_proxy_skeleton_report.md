# Phase 6A Proxy Skeleton Report

## Goal

Phase 6A builds the minimum Python-level ContractKV serving prototype:

`OpenAI chat request -> segment parser -> policy runtime -> lifecycle decision -> vLLM OpenAI API -> response + decision log`

This phase does not modify vLLM internals or real KV cache layout.

## Implementation

Core modules:

- `scripts/contractkv_segment_parser.py`
- `scripts/contractkv_policy_runtime.py`
- `scripts/contractkv_decision_logger.py`
- `scripts/contractkv_server_proxy.py`

The proxy preserves the upstream vLLM response body and adds side-channel logs:

- `results/runtime/contractkv_proxy_requests.jsonl`
- `results/runtime/contractkv_decision_logs.jsonl`

## Live vLLM Smoke

The proxy was tested against real vLLM OpenAI-compatible endpoints:

| Model | Status | Output format preserved | Proxy overhead ms |
| --- | ---: | --- | ---: |
| Qwen3-4B | 200 | true | 0.669 |
| Qwen3-8B | 200 | true | 0.656 |

Both requests returned normal OpenAI-style `choices`, and each request generated a ContractKV decision log.

## Boundary

This is a Python proxy skeleton. It validates serving-path attachment and logging, not throughput improvement.
