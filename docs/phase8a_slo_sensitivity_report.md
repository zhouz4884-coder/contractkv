# Phase 8A SLO Sensitivity Report

## Goal

Recompute Phase 7 live replay results under multiple TTFT SLO budgets without rerunning vLLM.

SLO buckets:

- 200 ms
- 300 ms
- 500 ms
- 800 ms
- 1000 ms

Output:

- `results/workload/slo_sensitivity_v0.csv`

## Results

Average across RULER, LongBench, and RepoBench:

| Policy | SLO ms | SLO violation | SLO-compliant req/s | Admitted req/s | Quality violation |
| --- | ---: | ---: | ---: | ---: | ---: |
| No-Contract | 200 | 0.840 | 2.890 | 16.420 | 0.000 |
| No-Contract | 300 | 0.020 | 16.108 | 16.420 | 0.000 |
| No-Contract | 500 | 0.017 | 16.171 | 16.420 | 0.000 |
| No-Contract | 800 | 0.017 | 16.171 | 16.420 | 0.000 |
| No-Contract | 1000 | 0.000 | 16.420 | 16.420 | 0.000 |
| ContractKV-Indep | 200 | 0.980 | 0.000 | 0.000 | 1.000 |
| ContractKV-Indep | 300 | 0.123 | 0.000 | 0.000 | 1.000 |
| ContractKV-Indep | 500 | 0.000 | 0.000 | 0.000 | 1.000 |
| ContractKV-Indep | 800 | 0.000 | 0.000 | 0.000 | 1.000 |
| ContractKV-Indep | 1000 | 0.000 | 0.000 | 0.000 | 1.000 |
| ContractKV-Joint | 200 | 0.890 | 1.943 | 16.230 | 0.000 |
| ContractKV-Joint | 300 | 0.037 | 15.667 | 16.230 | 0.000 |
| ContractKV-Joint | 500 | 0.000 | 16.230 | 16.230 | 0.000 |
| ContractKV-Joint | 800 | 0.000 | 16.230 | 16.230 | 0.000 |
| ContractKV-Joint | 1000 | 0.000 | 16.230 | 16.230 | 0.000 |

## Answers

Joint keeps quality violation at 0.0 for every SLO bucket.

Indep remains inadmissible for every SLO bucket because quality violation stays at 1.0. Relaxing latency alone cannot fix an unsafe independent precision/placement decision.

Joint's SLO-compliant goodput rises sharply as SLO is relaxed: 1.943 req/s at 200 ms, 15.667 req/s at 300 ms, and 16.230 req/s from 500 ms onward. This confirms that the 200 ms setting from Phase 7 was a strong stress configuration.

## Boundary

This report recomputes SLO labels from Phase 7 live replay rows. It does not rerun vLLM and does not claim production throughput.
