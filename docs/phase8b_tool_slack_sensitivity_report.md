# Phase 8B Tool-Slack Sensitivity Report

## Goal

Quantify how much tool slack is needed to hide KV-sized transfer proxy cost.

Slack buckets:

- 0 ms
- 10 ms
- 50 ms
- 100 ms
- 200 ms
- 500 ms

Transfer sizes:

- 128 MB
- 256 MB
- 512 MB
- 1024 MB

Output:

- `results/workload/tool_slack_sensitivity_v0.csv`

## Results

Slack-window residual stall:

| KV proxy size MB | 0 ms slack | 10 ms slack | 50 ms slack | 100 ms slack | 200 ms slack | 500 ms slack |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 128 | 10.199 | 0.199 | 0.000 | 0.000 | 0.000 | 0.000 |
| 256 | 20.354 | 10.354 | 0.000 | 0.000 | 0.000 | 0.000 |
| 512 | 40.666 | 30.666 | 0.000 | 0.000 | 0.000 | 0.000 |
| 1024 | 81.340 | 71.340 | 31.340 | 0.000 | 0.000 | 0.000 |

## Findings

Small KV movement can be hidden by short slack windows: 128 MB is almost fully hidden by 10 ms slack and fully hidden by 50 ms.

Large KV movement leaves residual stall unless slack is large enough: 1024 MB still leaves 31.340 ms residual stall with 50 ms slack and needs 100 ms slack to hide fully.

This supports the ContractKV premise: prefetch/offload cannot be a blind independent action. The controller must jointly consider segment risk, transfer size, and available tool slack.

## Boundary

This is a transfer proxy derived from CUDA pinned-memory copy measurements. It does not move real vLLM KV cache blocks.
