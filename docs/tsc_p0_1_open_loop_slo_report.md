# P0-1 Open-Loop SLO Service Evaluation

## Scope

Real vLLM Poisson and ON/OFF serving cells; every cell uses the frozen 1,125-request trace and three fresh-process repeats. Registration cost that is not hidden by tool slack is amortized into the SLO test.

## ContractKV versus native vLLM APC

| Model | Arrival | Load | SLO (ms) | SLO-goodput multiplier | Mean TTFT reduction | p99 TTFT reduction | New-prefill reduction | D0 completion | D2 completion |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| mistral | onoff | 80% | 500 | 0.74x | -2.82% | -0.85% | -2.55% | 100.00% | 100.00% |
| mistral | onoff | 80% | 1000 | 0.66x | -2.82% | -0.85% | -2.55% | 100.00% | 100.00% |
| mistral | onoff | 80% | 1500 | 0.92x | -2.82% | -0.85% | -2.55% | 100.00% | 100.00% |
| mistral | onoff | 80% | 3000 | 0.99x | -2.82% | -0.85% | -2.55% | 100.00% | 100.00% |
| mistral | poisson | 80% | 500 | 0.82x | -3.03% | -3.29% | -2.55% | 100.00% | 100.00% |
| mistral | poisson | 80% | 1000 | 0.75x | -3.03% | -3.29% | -2.55% | 100.00% | 100.00% |
| mistral | poisson | 80% | 1500 | 0.94x | -3.03% | -3.29% | -2.55% | 100.00% | 100.00% |
| mistral | poisson | 80% | 3000 | 0.99x | -3.03% | -3.29% | -2.55% | 100.00% | 100.00% |
| mistral | poisson | 100% | 500 | 0.78x | -4.69% | -5.05% | -2.58% | 99.94% | 100.00% |
| mistral | poisson | 100% | 1000 | 0.69x | -4.69% | -5.05% | -2.58% | 99.94% | 100.00% |
| mistral | poisson | 100% | 1500 | 0.91x | -4.69% | -5.05% | -2.58% | 99.94% | 100.00% |
| mistral | poisson | 100% | 3000 | 0.99x | -4.69% | -5.05% | -2.58% | 99.94% | 100.00% |
| mistral | poisson | 120% | 500 | 0.76x | -8.69% | -7.48% | -2.59% | 99.94% | 99.97% |
| mistral | poisson | 120% | 1000 | 0.66x | -8.69% | -7.48% | -2.59% | 99.94% | 99.97% |
| mistral | poisson | 120% | 1500 | 0.83x | -8.69% | -7.48% | -2.59% | 99.94% | 99.97% |
| mistral | poisson | 120% | 3000 | 0.92x | -8.69% | -7.48% | -2.59% | 99.94% | 99.97% |
| qwen | onoff | 80% | 500 | 0.56x | -2.58% | -4.72% | -1.60% | 99.94% | 99.97% |
| qwen | onoff | 80% | 1000 | 0.65x | -2.58% | -4.72% | -1.60% | 99.94% | 99.97% |
| qwen | onoff | 80% | 1500 | 0.87x | -2.58% | -4.72% | -1.60% | 99.94% | 99.97% |
| qwen | onoff | 80% | 3000 | 0.99x | -2.58% | -4.72% | -1.60% | 99.94% | 99.97% |
| qwen | poisson | 60% | 500 | 0.56x | -2.36% | -2.43% | -1.63% | 100.00% | 100.00% |
| qwen | poisson | 60% | 1000 | 0.75x | -2.36% | -2.43% | -1.63% | 100.00% | 100.00% |
| qwen | poisson | 60% | 1500 | 0.95x | -2.36% | -2.43% | -1.63% | 100.00% | 100.00% |
| qwen | poisson | 60% | 3000 | 1.00x | -2.36% | -2.43% | -1.63% | 100.00% | 100.00% |
| qwen | poisson | 80% | 500 | 0.56x | -1.67% | -3.98% | -1.63% | 100.00% | 100.00% |
| qwen | poisson | 80% | 1000 | 0.73x | -1.67% | -3.98% | -1.63% | 100.00% | 100.00% |
| qwen | poisson | 80% | 1500 | 0.93x | -1.67% | -3.98% | -1.63% | 100.00% | 100.00% |
| qwen | poisson | 80% | 3000 | 1.00x | -1.67% | -3.98% | -1.63% | 100.00% | 100.00% |
| qwen | poisson | 100% | 500 | 0.59x | -2.37% | -4.14% | -1.63% | 99.97% | 100.00% |
| qwen | poisson | 100% | 1000 | 0.71x | -2.37% | -4.14% | -1.63% | 99.97% | 100.00% |
| qwen | poisson | 100% | 1500 | 0.91x | -2.37% | -4.14% | -1.63% | 99.97% | 100.00% |
| qwen | poisson | 100% | 3000 | 0.99x | -2.37% | -4.14% | -1.63% | 99.97% | 100.00% |
| qwen | poisson | 120% | 500 | 0.58x | -4.26% | -7.20% | -1.63% | 100.00% | 99.97% |
| qwen | poisson | 120% | 1000 | 0.68x | -4.26% | -7.20% | -1.63% | 100.00% | 99.97% |
| qwen | poisson | 120% | 1500 | 0.87x | -4.26% | -7.20% | -1.63% | 100.00% | 99.97% |
| qwen | poisson | 120% | 3000 | 0.98x | -4.26% | -7.20% | -1.63% | 100.00% | 99.97% |

## Evidence boundary

Primary comparison rows: 36; observed SLO-goodput multiplier range: 0.56x-1.00x.
Marker sanity checks the serving path and is not official benchmark scoring. Full per-cell queue, GPU, block-pool, and transport fields remain in `results/tsc_service/open_loop_cell_summary_v0.csv`.

## Service-template locality

The natural mixed trace is retained as a low-locality boundary. The prospective locality sweep changes only authorized stable-template sharing; tenant-private suffixes and the arrival trace remain frozen.

| Model | Tenants/template | Policy | Load | SLO (ms) | Goodput multiplier | Mean TTFT reduction | p99 reduction | New-prefill reduction |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| mistral | 25 | D2-template-contractkv | 80% | 500 | 4.48x | 54.35% | 29.65% | 50.75% |
| mistral | 25 | D2-template-contractkv | 80% | 1000 | 1.48x | 54.35% | 29.65% | 50.75% |
| mistral | 25 | D2-template-contractkv | 80% | 1500 | 1.17x | 54.35% | 29.65% | 50.75% |
| mistral | 25 | D2-template-contractkv | 80% | 3000 | 1.00x | 54.35% | 29.65% | 50.75% |
| mistral | 25 | D2-template-contractkv | 100% | 500 | 4.91x | 57.66% | 44.72% | 50.74% |
| mistral | 25 | D2-template-contractkv | 100% | 1000 | 1.73x | 57.66% | 44.72% | 50.74% |
| mistral | 25 | D2-template-contractkv | 100% | 1500 | 1.32x | 57.66% | 44.72% | 50.74% |
| mistral | 25 | D2-template-contractkv | 100% | 3000 | 1.02x | 57.66% | 44.72% | 50.74% |
| mistral | 25 | D2-template-contractkv | 120% | 500 | 6.95x | 66.03% | 58.01% | 50.73% |
| mistral | 25 | D2-template-contractkv | 120% | 1000 | 2.55x | 66.03% | 58.01% | 50.73% |
| mistral | 25 | D2-template-contractkv | 120% | 1500 | 1.77x | 66.03% | 58.01% | 50.73% |
| mistral | 25 | D2-template-contractkv | 120% | 3000 | 1.14x | 66.03% | 58.01% | 50.73% |
| qwen | 1 | D2-template-contractkv | 80% | 500 | 0.69x | 2.10% | 0.96% | 0.80% |
| qwen | 1 | D2-template-contractkv | 80% | 1000 | 0.80x | 2.10% | 0.96% | 0.80% |
| qwen | 1 | D2-template-contractkv | 80% | 1500 | 0.97x | 2.10% | 0.96% | 0.80% |
| qwen | 1 | D2-template-contractkv | 80% | 3000 | 1.00x | 2.10% | 0.96% | 0.80% |
| qwen | 5 | D2-template-contractkv | 80% | 500 | 2.78x | 56.86% | 34.22% | 54.15% |
| qwen | 5 | D2-template-contractkv | 80% | 1000 | 1.36x | 56.86% | 34.22% | 54.15% |
| qwen | 5 | D2-template-contractkv | 80% | 1500 | 1.10x | 56.86% | 34.22% | 54.15% |
| qwen | 5 | D2-template-contractkv | 80% | 3000 | 1.00x | 56.86% | 34.22% | 54.15% |
| qwen | 25 | D1-frozen-safe | 60% | 500 | 4.34x | 91.79% | 95.26% | 98.15% |
| qwen | 25 | D1-frozen-safe | 60% | 1000 | 1.23x | 91.79% | 95.26% | 98.15% |
| qwen | 25 | D1-frozen-safe | 60% | 1500 | 1.03x | 91.79% | 95.26% | 98.15% |
| qwen | 25 | D1-frozen-safe | 60% | 3000 | 1.00x | 91.79% | 95.26% | 98.15% |
| qwen | 25 | D1-frozen-safe | 80% | 500 | 4.81x | 92.65% | 95.78% | 98.15% |
| qwen | 25 | D1-frozen-safe | 80% | 1000 | 1.40x | 92.65% | 95.78% | 98.15% |
| qwen | 25 | D1-frozen-safe | 80% | 1500 | 1.08x | 92.65% | 95.78% | 98.15% |
| qwen | 25 | D1-frozen-safe | 80% | 3000 | 1.00x | 92.65% | 95.78% | 98.15% |
| qwen | 25 | D1-frozen-safe | 100% | 500 | 6.04x | 93.66% | 96.55% | 98.15% |
| qwen | 25 | D1-frozen-safe | 100% | 1000 | 1.65x | 93.66% | 96.55% | 98.15% |
| qwen | 25 | D1-frozen-safe | 100% | 1500 | 1.17x | 93.66% | 96.55% | 98.15% |
| qwen | 25 | D1-frozen-safe | 100% | 3000 | 1.00x | 93.66% | 96.55% | 98.15% |
| qwen | 25 | D1-frozen-safe | 120% | 500 | 8.14x | 94.64% | 97.40% | 98.15% |
| qwen | 25 | D1-frozen-safe | 120% | 1000 | 2.09x | 94.64% | 97.40% | 98.15% |
| qwen | 25 | D1-frozen-safe | 120% | 1500 | 1.33x | 94.64% | 97.40% | 98.15% |
| qwen | 25 | D1-frozen-safe | 120% | 3000 | 1.02x | 94.64% | 97.40% | 98.15% |
| qwen | 25 | D1-frozen-safe | 140% | 500 | 13.36x | 96.32% | 98.29% | 98.15% |
| qwen | 25 | D1-frozen-safe | 140% | 1000 | 3.39x | 96.32% | 98.29% | 98.15% |
| qwen | 25 | D1-frozen-safe | 140% | 1500 | 1.92x | 96.32% | 98.29% | 98.15% |
| qwen | 25 | D1-frozen-safe | 140% | 3000 | 1.14x | 96.32% | 98.29% | 98.15% |
| qwen | 25 | D2-session-contractkv | 80% | 500 | 4.79x | 92.49% | 95.71% | 97.77% |
| qwen | 25 | D2-session-contractkv | 80% | 1000 | 1.40x | 92.49% | 95.71% | 97.77% |
| qwen | 25 | D2-session-contractkv | 80% | 1500 | 1.08x | 92.49% | 95.71% | 97.77% |
| qwen | 25 | D2-session-contractkv | 80% | 3000 | 1.00x | 92.49% | 95.71% | 97.77% |
| qwen | 25 | D2-template-contractkv | 60% | 500 | 4.35x | 91.82% | 95.32% | 98.15% |
| qwen | 25 | D2-template-contractkv | 60% | 1000 | 1.23x | 91.82% | 95.32% | 98.15% |
| qwen | 25 | D2-template-contractkv | 60% | 1500 | 1.03x | 91.82% | 95.32% | 98.15% |
| qwen | 25 | D2-template-contractkv | 60% | 3000 | 1.00x | 91.82% | 95.32% | 98.15% |
| qwen | 25 | D2-template-contractkv | 80% | 500 | 4.81x | 92.62% | 95.78% | 98.15% |
| qwen | 25 | D2-template-contractkv | 80% | 1000 | 1.40x | 92.62% | 95.78% | 98.15% |
| qwen | 25 | D2-template-contractkv | 80% | 1500 | 1.08x | 92.62% | 95.78% | 98.15% |
| qwen | 25 | D2-template-contractkv | 80% | 3000 | 1.00x | 92.62% | 95.78% | 98.15% |
| qwen | 25 | D2-template-contractkv | 100% | 500 | 6.04x | 93.63% | 96.53% | 98.15% |
| qwen | 25 | D2-template-contractkv | 100% | 1000 | 1.65x | 93.63% | 96.53% | 98.15% |
| qwen | 25 | D2-template-contractkv | 100% | 1500 | 1.17x | 93.63% | 96.53% | 98.15% |
| qwen | 25 | D2-template-contractkv | 100% | 3000 | 1.00x | 93.63% | 96.53% | 98.15% |
| qwen | 25 | D2-template-contractkv | 120% | 500 | 8.14x | 94.58% | 97.33% | 98.15% |
| qwen | 25 | D2-template-contractkv | 120% | 1000 | 2.09x | 94.58% | 97.33% | 98.15% |
| qwen | 25 | D2-template-contractkv | 120% | 1500 | 1.33x | 94.58% | 97.33% | 98.15% |
| qwen | 25 | D2-template-contractkv | 120% | 3000 | 1.02x | 94.58% | 97.33% | 98.15% |
| qwen | 25 | D2-template-contractkv | 140% | 500 | 13.36x | 96.32% | 98.23% | 98.15% |
| qwen | 25 | D2-template-contractkv | 140% | 1000 | 3.39x | 96.32% | 98.23% | 98.15% |
| qwen | 25 | D2-template-contractkv | 140% | 1500 | 1.92x | 96.32% | 98.23% | 98.15% |
| qwen | 25 | D2-template-contractkv | 140% | 3000 | 1.14x | 96.32% | 98.23% | 98.15% |

## Certificate fan-out

| Model | Policy | Tenants/template | Verifier calls | Commits | Fan-out | Unhidden ms/request | Mean TTFT reduction |
|---|---|---:|---:|---:|---:|---:|---:|
| mistral | D2-template-contractkv | 25 | 3.0 | 3.0 | 375.0 | 3.207 | 54.35% |
| qwen | D2-template-contractkv | 1 | 125.0 | 124.0 | 9.0 | 99.809 | 2.10% |
| qwen | D2-template-contractkv | 5 | 25.0 | 25.0 | 45.0 | 18.085 | 56.86% |
| qwen | D1-frozen-safe | 25 | 0.0 | 5.0 | 1125.0 | 0.000 | 92.65% |
| qwen | D2-session-contractkv | 25 | 125.0 | 125.0 | 9.0 | 25.049 | 92.49% |
| qwen | D2-template-contractkv | 25 | 5.0 | 5.0 | 225.0 | 3.236 | 92.62% |

## Hierarchical uncertainty

Confidence intervals resample fresh process, service template, and tenant session. p99 is reported as the range across the three fresh repeats rather than by pooling all requests.

| Model | SLO (ms) | Mean TTFT reduction (95% CI) | p99 reduction repeat range | New-prefill repeat range | SLO-goodput delta req/s (95% CI) | Multiplier (95% CI when identifiable) |
|---|---:|---:|---:|---:|---:|---:|
| qwen | 500 | 92.62% [91.68%, 93.31%] | [95.70%, 95.83%] | [98.15%, 98.15%] | 0.658 [0.539, 0.765] | 4.81x [2.85x, 12.61x] |
| qwen | 1000 | 92.62% [91.68%, 93.31%] | [95.70%, 95.83%] | [98.15%, 98.15%] | 0.238 [0.198, 0.275] | 1.40x [1.31x, 1.49x] |
| qwen | 1500 | 92.62% [91.68%, 93.31%] | [95.70%, 95.83%] | [98.15%, 98.15%] | 0.060 [0.047, 0.073] | 1.08x [1.06x, 1.10x] |
| qwen | 3000 | 92.62% [91.68%, 93.31%] | [95.70%, 95.83%] | [98.15%, 98.15%] | 0.001 [0.001, 0.001] | 1.00x [1.00x, 1.00x] |
| mistral | 500 | 54.37% [34.25%, 72.02%] | [29.20%, 30.53%] | [50.74%, 50.82%] | 0.340 [0.129, 0.538] | 4.48x [ratio CI not identifiable: clustered D0 crosses zero] |
| mistral | 1000 | 54.37% [34.25%, 72.02%] | [29.20%, 30.53%] | [50.74%, 50.82%] | 0.247 [0.187, 0.302] | 1.48x [1.35x, 1.63x] |
| mistral | 1500 | 54.37% [34.25%, 72.02%] | [29.20%, 30.53%] | [50.74%, 50.82%] | 0.119 [0.089, 0.145] | 1.17x [1.12x, 1.22x] |
| mistral | 3000 | 54.37% [34.25%, 72.02%] | [29.20%, 30.53%] | [50.74%, 50.82%] | 0.003 [0.001, 0.005] | 1.00x [1.00x, 1.01x] |

The former single-number 1,500-ms sustainable-capacity ratio is intentionally omitted: native D0 is already below that p99 gate at the lowest measured load, so its denominator is zero. The paper-facing result is the complete 60%-140% load-p99-goodput curve. Loads above 140% remain an overload appendix and are not headline evidence.

## Locality-residency operating region

Exact vLLM eviction counts are unavailable in the scheduler probe and are not fabricated. Reuse distance, prefix-hit ratio, new-prefill work, and zero-hit-after-prior-template requests are reported instead.

| Active templates | Arrival order | Mean reuse distance | Prefix-hit ratio | New-prefill reduction | Net mean TTFT reduction | SLO-goodput multiplier |
|---:|---|---:|---:|---:|---:|---:|
| 5 | round_robin | 5.0 | 98.19% | 98.15% | 93.69% | 1.15x |
| 5 | zipf | 5.0 | 98.30% | 98.26% | 94.26% | 1.21x |
| 25 | round_robin | 25.0 | 0.00% | -0.00% | 0.36% | 1.00x |
| 25 | zipf | 22.7 | 83.44% | 83.18% | 84.63% | 1.19x |
| 50 | round_robin | 50.0 | 0.00% | 0.00% | 0.64% | 0.99x |
| 50 | zipf | 37.5 | 69.57% | 69.14% | 73.40% | 1.22x |
