# Phase 17D: Live Verifier Quiescence

The verifier was admitted only after foreground work became visible, with a 32-token maximum verifier chunk and a 10 ms p95 foreground penalty budget. The corrected live Qwen3-4B result is in [phase17_verifier_quiescence_summary_v0.csv](../results/hard_systems/phase17_verifier_quiescence_summary_v0.csv).

| Condition | Active success | Verifier success | Mean TTFT | p95 TTFT | p95 penalty |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 60 / 60 | n/a | 110.82 ms | 192.74 ms | 0.00 ms |
| Live verifier | 60 / 60 | 6 / 6 | 115.37 ms | 199.60 ms | 6.87 ms |

The gate passed: no mixed rounds, max verifier chunk 32 tokens, 114 idle-hysteresis rejections, and zero collisions.

## Boundary

This is a non-interference result for compact teacher-forced shadow verification under foreground load. It makes no acceleration claim.
