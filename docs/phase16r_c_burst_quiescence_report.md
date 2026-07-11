# Phase 16R-C: Burst-Aware Quiescence Gate

## Objective

Phase 16R-C adds foreground activity timestamps, idle hysteresis, collision
backoff, a KV watermark, and a 32-token cap at both initial admission and running
iterations. It is an independent scheduler node and does not inspect verifier or
PSTP decisions beyond the explicit `shadow_work` classification.

## Fair Live Design

Each grace configuration used a fresh Qwen3-4B vLLM server. Every condition was
warmed up, condition order alternated by seed, and prompts used distinct IDs.
For each grace, the measured set contained 60 baseline foreground requests and a
second condition with 60 foreground plus 6 shadow requests. The `grace=0` run also
synchronized one burst to the first observed shadow round to exercise backoff.

## Result

| Idle grace | Shadow p95 TTFT | Delta vs paired baseline | Collisions | Hysteresis rejects | Shadow completion |
|---:|---:|---:|---:|---:|---:|
| 0 ms | 277.13 ms | -0.22 ms | 1 | 0 | 100% |
| 10 ms | 275.55 ms | -18.29 ms | 0 | 104 | 100% |
| 25 ms | 269.83 ms | -12.51 ms | 0 | 308 | 100% |

All 180 shadow-condition foreground requests completed. Across all configurations:

- foreground and shadow tokens shared zero scheduler rounds;
- the maximum per-request shadow chunk was exactly 32 tokens;
- foreground waiting/running gates were observed;
- the synchronized collision produced an observable 1 ms backoff;
- all 18 shadow requests completed.

The small negative TTFT deltas are run-to-run variation and are not claimed as a
speedup. The defensible result is that this workload observed no p95 foreground
penalty while completing all shadow work. Ten milliseconds is the practical
Pareto point here: it activated hysteresis and avoided the synchronized zero-grace
collision without requiring the larger 25 ms delay.

Evidence is in `results/hard_systems/phase16r_quiescence_pareto_v0.csv`; the three
raw and per-grace summary CSVs preserve all request records.

## Claim Boundary

This is a real vLLM V1 admission/scheduling result on one model and one burst
shape. It does not establish production tail behavior across arbitrary arrival
distributions or a verifier-aware priority policy.
