# P0-2 Multi-Tenant Isolation and Fairness

## Forty-tenant sharing curve

| Policy | Authorized sharing | Completion | Mean TTFT (ms) | p95 TTFT (ms) | Steady SLO req/s | Cold-start SLO req/s | Jain fairness | Verifier calls | Fan-out | Unauthorized reuse | Dynamic suffix reuse | Scope-invalid admission |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| D0-native-apc | 0% | 100.00% | 1369.3 | 1942.7 | 1.001 | 1.001 | 0.6676 | 0.0 | 360.0 | 0 | 0 | 0 |
| D2-full-contractkv | 0% | 100.00% | 1413.2 | 2043.7 | 0.986 | 0.501 | 0.6450 | 40.0 | 9.0 | 0 | 0 | 0 |
| D0-native-apc | 25% | 100.00% | 1373.6 | 1950.4 | 1.000 | 1.000 | 0.6578 | 0.0 | 360.0 | 0 | 0 | 0 |
| D2-full-contractkv | 25% | 100.00% | 1075.5 | 1924.2 | 1.480 | 0.815 | 0.7518 | 31.0 | 11.6 | 0 | 0 | 0 |
| D0-native-apc | 50% | 100.00% | 1390.2 | 1955.6 | 1.005 | 1.005 | 0.6569 | 0.0 | 360.0 | 0 | 0 | 0 |
| D2-full-contractkv | 50% | 100.00% | 783.8 | 1918.7 | 2.226 | 1.383 | 0.8068 | 21.0 | 17.1 | 0 | 0 | 0 |
| D0-native-apc | 75% | 100.00% | 1357.5 | 1954.5 | 1.046 | 1.046 | 0.6707 | 0.0 | 360.0 | 0 | 0 | 0 |
| D2-full-contractkv | 75% | 100.00% | 90.4 | 123.0 | 11.013 | 5.550 | 1.0000 | 11.0 | 32.7 | 0 | 0 | 0 |
| D0-native-apc | 100% | 100.00% | 1364.5 | 1950.5 | 1.064 | 1.064 | 0.6663 | 0.0 | 360.0 | 0 | 0 | 0 |
| D2-full-contractkv | 100% | 100.00% | 90.8 | 122.7 | 10.984 | 9.865 | 1.0000 | 1.0 | 360.0 | 0 | 0 | 0 |

## Safety interpretation

Tenant identity, authorization scope, policy hash, and private suffix are part of the real prompt/cache key. Both steady-state and registration-amortized goodput are reported; ContractKV is not claimed to implement priority scheduling.
