# Phase 14D Open-Loop Capacity Evaluation

## Method

The runner uses a central Poisson arrival clock and launches each OpenAI-compatible vLLM request independently of completion. A point is stable only when completion is at least 99%, p95 TTFT meets the SLO, second-half scheduler-wait slope is at most 0.02 seconds per second, and the drain leaves no backlog.

## Capacity Separation

With 4K shared context, a 2 s TTFT SLO, and a 60-second offered-load window, CAPOSC at 24 req/s passes all four stability conditions in all three independent seeds:

| CAPOSC 24 req/s | Seed 14014 | Seed 24014 | Seed 34014 |
| --- | ---: | ---: | ---: |
| Completion | 100% | 100% | 100% |
| p95 TTFT | 1,408 ms | 1,372 ms | 1,396 ms |
| SLO goodput | 23.98 req/s | 24.15 req/s | 23.15 req/s |
| End backlog | 0 | 0 | 0 |

The same runner rejects CAPOSC 32 req/s over 60 seconds because it leaves more than 220 outstanding requests in every seed, even though the short 30-second sweep looked stable. Raw order at 0.2 req/s remains borderline: two seeds pass, one has 2,070 ms p95 TTFT and a wait slope slightly above the threshold. It must not yet be reported as a final raw capacity knee.

The evidence is already a strong live separation: at 24 req/s CAPOSC pre-fills about 36 tokens per request after priming, while raw examples pre-fill about 4,133 tokens. A final paper capacity-lift number requires a longer low-rate raw run to locate an all-seed stable raw knee and sufficient completed samples; this report does not claim that final ratio.

## Artifacts

- `scripts/phase14d_open_loop_capacity.py`
- `results/hard_systems/phase14d_capacity_coarse_summary_v0.csv`
- `results/hard_systems/phase14d_capacity_final2_summary_v0.csv`
