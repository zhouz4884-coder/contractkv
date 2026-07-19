# P1-1 Service Density and Consolidation

## Density sweep

| Policy | Tenants | Completion | SLO req/s | Mean TTFT (ms) | p95 TTFT (ms) | Peak used blocks | Minimum free blocks |
|---|---:|---:|---:|---:|---:|---:|---:|
| D0-native-apc | 10 | 100.00% | 0.900 | 1384.5 | 1995.4 | 525.7 | 1860.3 |
| D2-full-contractkv | 10 | 100.00% | 9.408 | 95.9 | 128.1 | 146.0 | 2240.0 |
| D0-native-apc | 20 | 100.00% | 1.032 | 1399.1 | 1984.3 | 530.0 | 1856.0 |
| D2-full-contractkv | 20 | 100.00% | 10.781 | 94.2 | 124.4 | 149.0 | 2237.0 |
| D0-native-apc | 30 | 100.00% | 1.059 | 1354.8 | 1968.1 | 530.0 | 1856.0 |
| D2-full-contractkv | 30 | 100.00% | 10.532 | 91.4 | 124.0 | 149.0 | 2237.0 |
| D0-native-apc | 40 | 100.00% | 1.073 | 1350.2 | 1955.2 | 530.0 | 1856.0 |
| D2-full-contractkv | 40 | 100.00% | 11.057 | 90.2 | 122.9 | 149.0 | 2237.0 |
| D0-native-apc | 60 | 100.00% | 1.112 | 1304.1 | 1937.4 | 530.0 | 1856.0 |
| D2-full-contractkv | 60 | 100.00% | 11.072 | 90.4 | 121.1 | 149.0 | 2237.0 |
| D0-native-apc | 80 | 100.00% | 1.152 | 1219.9 | 1933.0 | 530.0 | 1856.0 |
| D2-full-contractkv | 80 | 100.00% | 11.033 | 90.0 | 119.6 | 149.0 | 2237.0 |

Capacity failures are retained as results rather than aborting the sweep. Density is reported in tenants and real vLLM block-pool occupancy; no token-to-GiB conversion is invented when a physical byte mapping is unavailable.
