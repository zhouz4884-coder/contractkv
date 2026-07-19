# P1-2 Gold/Silver/Bronze Service Classes

## Fully authorized 40-tenant cell

| Policy | Class | Completion | SLO req/s | Mean TTFT (ms) | p95 TTFT (ms) | Weighted goodput | Jain fairness |
|---|---|---:|---:|---:|---:|---:|---:|
| D0-native-apc | Bronze | 100.00% | 0.585 | 1388.5 | 1957.7 | 0.585 | 0.6663 |
| D0-native-apc | Gold | 100.00% | 0.032 | 1330.2 | 1951.0 | 0.095 | 0.6663 |
| D0-native-apc | Silver | 100.00% | 0.447 | 1377.4 | 1943.9 | 0.894 | 0.6663 |
| D2-full-contractkv | Bronze | 100.00% | 3.570 | 91.6 | 122.6 | 3.570 | 1.0000 |
| D2-full-contractkv | Gold | 100.00% | 3.844 | 90.6 | 122.4 | 11.533 | 1.0000 |
| D2-full-contractkv | Silver | 100.00% | 3.570 | 90.1 | 122.5 | 7.139 | 1.0000 |

Gold/Silver/Bronze use 750/1500/3000 ms TTFT SLOs with weights 3/2/1. This evaluates whether prefix optimization creates severe class or tenant unfairness; it is not a claim of SLA-aware scheduling.
