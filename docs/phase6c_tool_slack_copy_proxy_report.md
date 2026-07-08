# Phase 6C Tool-Slack Copy Proxy Report

## Goal

Evaluate host/GPU transfer scheduling with KV-sized tensor proxies before touching real vLLM KV cache.

Implemented script:

- `scripts/runtime_kv_tensor_proxy.py`

Output:

- `results/runtime/tool_slack_copy_proxy_v0.csv`

## Configuration

Modes:

- `no_copy`
- `copy_on_critical_path`
- `copy_in_tool_slack_window`

KV proxy sizes:

- 128 MB
- 256 MB
- 512 MB
- 1024 MB

The server run used pinned host memory and CUDA stream transfer proxy.

## Results

| KV size MB | Critical-path latency ms | Slack-window residual stall ms | Critical-path bandwidth GB/s |
| ---: | ---: | ---: | ---: |
| 128 | 10.347 | 0.173 | 12.256 |
| 256 | 20.508 | 10.367 | 12.283 |
| 512 | 40.894 | 30.639 | 12.295 |
| 1024 | 81.774 | 71.270 | 12.294 |

## Findings

Critical-path copy directly increases request-side latency. A 10 ms slack window hides most of a 128 MB transfer, but larger transfers leave residual stall. This supports ContractKV's scheduler premise: placement and prefetch/offload should be aligned with tool-slack windows instead of being treated as free background operations.

## Boundary

This is a KV-sized tensor proxy. It does not copy real vLLM KV cache blocks.
