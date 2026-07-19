# P0-3 Verification Economics

## Live boundary points

| Model | Live lanes | Accepted | Fail-closed fallback | Positive lanes | Positive fraction | Mean registration (ms) | Mean unhidden verification (ms) | Mean net benefit (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Mistral-7B-Instruct-v0.3 | 42 | 40 | 2 | 37 | 88.10% | 17391.4 | 14697.7 | 49177.0 |
| Qwen3-8B | 42 | 42 | 0 | 34 | 80.95% | 18747.6 | 16022.5 | 49952.0 |

## Operating-region definition

The analytical contour interpolates only measured registration cost and measured per-turn savings. A rejected certificate executes raw-order fallback and remains in the live table; rejection is not converted into a false compiled-policy success. Live boundary lanes remain separately identifiable, and the offline contour is not presented as serving throughput.
