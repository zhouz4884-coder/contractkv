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
| qwen | 25 | D1-frozen-safe | 20% | 500 | 3.41x | 89.73% | 92.62% | 98.15% |
| qwen | 25 | D1-frozen-safe | 20% | 1000 | 1.04x | 89.73% | 92.62% | 98.15% |
| qwen | 25 | D1-frozen-safe | 20% | 1500 | 1.00x | 89.73% | 92.62% | 98.15% |
| qwen | 25 | D1-frozen-safe | 20% | 3000 | 1.00x | 89.73% | 92.62% | 98.15% |
| qwen | 25 | D1-frozen-safe | 40% | 500 | 3.81x | 90.83% | 94.64% | 98.15% |
| qwen | 25 | D1-frozen-safe | 40% | 1000 | 1.11x | 90.83% | 94.64% | 98.15% |
| qwen | 25 | D1-frozen-safe | 40% | 1500 | 1.01x | 90.83% | 94.64% | 98.15% |
| qwen | 25 | D1-frozen-safe | 40% | 3000 | 1.00x | 90.83% | 94.64% | 98.15% |
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
| qwen | 25 | D1-frozen-safe | 200% | 500 | 659.06x | 99.88% | 99.89% | 98.15% |
| qwen | 25 | D1-frozen-safe | 200% | 1000 | 109.84x | 99.88% | 99.89% | 98.15% |
| qwen | 25 | D1-frozen-safe | 200% | 1500 | 59.91x | 99.88% | 99.89% | 98.15% |
| qwen | 25 | D1-frozen-safe | 200% | 3000 | 47.08x | 99.88% | 99.89% | 98.15% |
| qwen | 25 | D1-frozen-safe | 400% | 500 | 2179.65x | 99.96% | 99.96% | 98.15% |
| qwen | 25 | D1-frozen-safe | 400% | 1000 | 1089.83x | 99.96% | 99.96% | 98.15% |
| qwen | 25 | D1-frozen-safe | 400% | 1500 | 726.55x | 99.96% | 99.96% | 98.15% |
| qwen | 25 | D1-frozen-safe | 400% | 3000 | 192.33x | 99.96% | 99.96% | 98.15% |
| qwen | 25 | D1-frozen-safe | 600% | 500 | 2597.93x | 99.95% | 99.96% | 98.15% |
| qwen | 25 | D1-frozen-safe | 600% | 1000 | 1559.04x | 99.95% | 99.96% | 98.15% |
| qwen | 25 | D1-frozen-safe | 600% | 1500 | 865.98x | 99.95% | 99.96% | 98.15% |
| qwen | 25 | D1-frozen-safe | 600% | 3000 | 371.13x | 99.95% | 99.96% | 98.15% |
| qwen | 25 | D1-frozen-safe | 800% | 500 | 3158.25x | 99.95% | 99.96% | 98.14% |
| qwen | 25 | D1-frozen-safe | 800% | 1000 | 3158.25x | 99.95% | 99.96% | 98.14% |
| qwen | 25 | D1-frozen-safe | 800% | 1500 | 1052.75x | 99.95% | 99.96% | 98.14% |
| qwen | 25 | D1-frozen-safe | 800% | 3000 | 557.43x | 99.95% | 99.96% | 98.14% |
| qwen | 25 | D2-template-contractkv | 20% | 500 | 3.41x | 89.65% | 92.58% | 98.15% |
| qwen | 25 | D2-template-contractkv | 20% | 1000 | 1.04x | 89.65% | 92.58% | 98.15% |
| qwen | 25 | D2-template-contractkv | 20% | 1500 | 1.00x | 89.65% | 92.58% | 98.15% |
| qwen | 25 | D2-template-contractkv | 20% | 3000 | 1.00x | 89.65% | 92.58% | 98.15% |
| qwen | 25 | D2-template-contractkv | 40% | 500 | 3.81x | 90.86% | 94.63% | 98.15% |
| qwen | 25 | D2-template-contractkv | 40% | 1000 | 1.11x | 90.86% | 94.63% | 98.15% |
| qwen | 25 | D2-template-contractkv | 40% | 1500 | 1.01x | 90.86% | 94.63% | 98.15% |
| qwen | 25 | D2-template-contractkv | 40% | 3000 | 1.00x | 90.86% | 94.63% | 98.15% |
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
| qwen | 25 | D2-template-contractkv | 200% | 500 | 659.07x | 99.88% | 99.89% | 98.15% |
| qwen | 25 | D2-template-contractkv | 200% | 1000 | 109.85x | 99.88% | 99.89% | 98.15% |
| qwen | 25 | D2-template-contractkv | 200% | 1500 | 59.92x | 99.88% | 99.89% | 98.15% |
| qwen | 25 | D2-template-contractkv | 200% | 3000 | 47.08x | 99.88% | 99.89% | 98.15% |
| qwen | 25 | D2-template-contractkv | 400% | 500 | 2179.66x | 99.96% | 99.96% | 98.15% |
| qwen | 25 | D2-template-contractkv | 400% | 1000 | 1089.83x | 99.96% | 99.96% | 98.15% |
| qwen | 25 | D2-template-contractkv | 400% | 1500 | 726.55x | 99.96% | 99.96% | 98.15% |
| qwen | 25 | D2-template-contractkv | 400% | 3000 | 192.33x | 99.96% | 99.96% | 98.15% |
| qwen | 25 | D2-template-contractkv | 600% | 500 | 2598.04x | 99.95% | 99.96% | 98.15% |
| qwen | 25 | D2-template-contractkv | 600% | 1000 | 1559.11x | 99.95% | 99.96% | 98.15% |
| qwen | 25 | D2-template-contractkv | 600% | 1500 | 866.01x | 99.95% | 99.96% | 98.15% |
| qwen | 25 | D2-template-contractkv | 600% | 3000 | 371.15x | 99.95% | 99.96% | 98.15% |
| qwen | 25 | D2-template-contractkv | 800% | 500 | 3158.42x | 99.95% | 99.96% | 98.14% |
| qwen | 25 | D2-template-contractkv | 800% | 1000 | 3158.42x | 99.95% | 99.96% | 98.14% |
| qwen | 25 | D2-template-contractkv | 800% | 1500 | 1052.81x | 99.95% | 99.96% | 98.14% |
| qwen | 25 | D2-template-contractkv | 800% | 3000 | 557.46x | 99.95% | 99.96% | 98.14% |

## Certificate fan-out

| Model | Policy | Tenants/template | Verifier calls | Commits | Fan-out | Unhidden ms/request | Mean TTFT reduction |
|---|---|---:|---:|---:|---:|---:|---:|
| mistral | D2-template-contractkv | 25 | 3.0 | 3.0 | 375.0 | 3.207 | 54.35% |
| qwen | D2-template-contractkv | 1 | 125.0 | 124.0 | 9.0 | 99.809 | 2.10% |
| qwen | D2-template-contractkv | 5 | 25.0 | 25.0 | 45.0 | 18.085 | 56.86% |
| qwen | D1-frozen-safe | 25 | 0.0 | 5.0 | 1125.0 | 0.000 | 92.65% |
| qwen | D2-template-contractkv | 25 | 5.0 | 5.0 | 225.0 | 3.236 | 92.62% |

## SLO-sustainable service capacity

The capacity is the largest frozen arrival-rate fraction for which all three fresh processes complete every request with zero quality/drop events and p99 TTFT at or below 1,500 ms.

| Model | Policy | Sustainable load | Uplift vs native |
|---|---|---:|---:|
| mistral | D0-native-apc | 0.00 | unbounded_by_grid |
| mistral | D2-template-contractkv | 0.00 | unbounded_by_grid |
| qwen | D0-native-apc | 0.00 | unbounded_by_grid |
| qwen | D1-frozen-safe | 8.00 | unbounded_by_grid |
| qwen | D2-template-contractkv | 8.00 | unbounded_by_grid |

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
