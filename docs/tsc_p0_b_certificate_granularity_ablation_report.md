# P0-B Certificate-Object Granularity Ablation

## Controlled setup

Qwen3-8B, 25 tenants per service template, the identical frozen 1,125-request trace, 80% offered load, and three fresh processes. D0, D1, D2-Session, and D2-Template use the same prompt layouts within their safe-layout class; only certificate granularity changes between the two D2 rows.

| Policy | Verifier calls | Commits | Fan-out | Unhidden verify ms/request | New-prefill tokens | Prefix-hit ratio | Mean/p99 TTFT (ms) | 1500-ms SLO req/s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| D0-native-apc | 0.0 | 0.0 | 1125.0 | 0.000 | 2250.2 | 2.18% | 852.4/2084.8 | 0.770 |
| D1-frozen-safe | 0.0 | 5.0 | 1125.0 | 0.000 | 41.7 | 98.19% | 62.6/87.9 | 0.831 |
| D2-session-contractkv | 125.0 | 125.0 | 9.0 | 25.049 | 50.2 | 97.82% | 64.0/89.5 | 0.831 |
| D2-template-contractkv | 5.0 | 5.0 | 225.0 | 3.236 | 41.7 | 98.19% | 62.9/88.0 | 0.831 |

## Causal conclusion

Overall gate: **PASS**. D2 session/template new-prefill delta: 8.5 tokens (0.37% of prompt). Template verifier calls lower: True; template verification cost per future request lower: True.

The ablation isolates the economic effect of certificate-object granularity: service-template certificates amortize one verification across authorized sessions without changing the layout or manufacturing additional prefix hits. Quality, dynamic-suffix isolation, and cross-domain isolation remain unchanged.
