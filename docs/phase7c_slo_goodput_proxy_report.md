# Phase 7C SLO Goodput Proxy Report

## Goal

Convert live replay rows into SLO goodput proxy metrics.

Output:

- `results/workload/slo_goodput_proxy_v0.csv`

## Key Questions

1. Does Joint keep the risk budget legal?
2. Is controller overhead still small?
3. Does slack-window copy reduce TTFT impact compared with critical-path copy?
4. Does Joint outperform Indep under SLO and quality constraints?

## Answers

Joint keeps the risk budget legal: quality violation rate is 0.0 across RULER, LongBench, and RepoBench. Indep violates the quality budget for every replayed request.

Controller overhead remains small: the live replay mean controller overhead is below 1 ms for Joint.

Slack-window copy reduces residual stall: Joint averages 12.228 ms residual stall, compared with 40.666 ms for the critical-path copy used by Indep.

Joint has higher admitted and compliant goodput than Indep because Indep has zero admitted requests under the quality budget. No-Contract has no ContractKV copy or risk policy, so it is a useful serving baseline but not a segment lifecycle policy.

## Selected Goodput Proxy Rows

| Dataset | Policy | Admitted req/s | SLO-compliant req/s | Quality violation | SLO violation | Mean residual stall ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| LongBench | No-Contract | 18.720 | 7.114 | 0.000 | 0.620 | 0.000 |
| LongBench | ContractKV-Indep | 0.000 | 0.000 | 1.000 | 0.940 | 40.666 |
| LongBench | ContractKV-Joint | 18.607 | 4.280 | 0.000 | 0.770 | 12.126 |
| RULER | ContractKV-Indep | 0.000 | 0.000 | 1.000 | 1.000 | 40.666 |
| RULER | ContractKV-Joint | 14.581 | 0.000 | 0.000 | 1.000 | 14.266 |
| RepoBench | ContractKV-Indep | 0.000 | 0.000 | 1.000 | 1.000 | 40.666 |
| RepoBench | ContractKV-Joint | 15.502 | 1.550 | 0.000 | 0.900 | 10.700 |

## Boundary

This is SLO goodput proxy evaluation. It does not claim true KV placement, true KV-cache memory savings, or production throughput.
