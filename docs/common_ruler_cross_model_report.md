# ContractKV Common-Scope Cross-Model RULER Replay

## Decision

The common-scope cross-model experiment is complete. Qwen3-8B,
Mistral-7B-Instruct-v0.3, and Llama-3.1-8B-Instruct all show large, safe
ContractKV gains on the exact same frozen 30-session RULER scope. This removes
the sample-asymmetry caveat from the earlier qualified-scope comparison.

## Frozen protocol

All three models consume the session file committed by SHA-256
`7fe10a55f82056125b6acb478aa24bd4883c12c4f6bfd19b3dedfd1f6e13f616`.
The protocol is fixed before the Qwen/Mistral runs:

- 30 source-group-disjoint `RULER:niah_single_1` sessions;
- 10 turns/session and 270 measured future requests/model/repeat;
- frozen L3 layout, with no requalification or threshold changes;
- raw order versus full online ContractKV;
- stable-word limit 1500, output limit 96, concurrency 2, SLO 1500 ms;
- float16, max model length 8192, max sequences 2, one RTX 3090/cell;
- three fresh raw/ContractKV process pairs with GPU assignment reversed on the
  second repeat.

The complete matrix contains 18 fresh server processes and 5,400 live requests.

## Common-scope result

| Model | Net mean TTFT reduction (session-cluster 95% CI) | TTFT speedup | p95 TTFT reduction | New-prefill reduction | Prefill-work speedup | SLO goodput raw -> ContractKV | Goodput multiplier |
|---|---:|---:|---:|---:|---:|---:|---:|
| Qwen3-8B | 86.64% [86.16%, 87.10%] | 7.48x | 85.37% | 96.71% | 30.38x | 2.42 -> 6.33 req/s | 2.61x |
| Mistral-7B | 87.41% [87.06%, 87.79%] | 7.94x | 85.95% | 95.86% | 24.17x | 2.67 -> 8.31 req/s | 3.11x |
| Llama-3.1-8B | 85.97% [85.63%, 86.29%] | 7.13x | 84.13% | 95.45% | 21.96x | 3.42 -> 14.42 req/s | 4.22x |
| Model-stratified macro | 86.67% [86.44%, 86.90%] | 7.50x | n/a | 96.01% | 25.04x | 2.84 -> 9.69 req/s | 3.31x |

The model-stratified bootstrap resamples fresh-process repeats and sessions
inside each model before taking the model-level macro average. It does not treat
requests from one session as independent observations.

## Safety and quality

| Model | Paired future outputs | Certificate coverage | Raw score | ContractKV score | Quality violations | Scope-invalid admitted |
|---|---:|---:|---:|---:|---:|---:|
| Qwen3-8B | 810 | 100% | 1.0 | 1.0 | 0 | 0 |
| Mistral-7B | 810 | 100% | 1.0 | 1.0 | 0 | 0 |
| Llama-3.1-8B | 810 | 100% | 1.0 | 1.0 | 0 | 0 |
| Total | 2,430 | 100% | 1.0 | 1.0 | 0 | 0 |

All 5,400 live requests complete. The result therefore combines symmetric
performance measurement with prospective qualification and paired output
scoring, rather than reporting a performance-only successful subset.

## Interpretation

This experiment supports a clean cross-model statement: within one
prospectively frozen, shared qualified workflow scope, ContractKV reduces net
mean TTFT by 85.97%-87.41% and deterministic new-prefill work by
95.45%-96.71% across three model families. The narrow spread is evidence that
the layout/prefix-reuse mechanism is not an artifact of a favorable RULER split
or one tokenizer/model implementation.

The relative SLO-goodput multiplier differs because each model has a different
raw decode/prefill rate and batching trajectory. It should not be interpreted as
one model providing a stronger ContractKV mechanism than another.

## Failure diagnosis during execution

The first Qwen raw server failed before request execution because two concurrent
same-model servers wrote the same Torch/vLLM compile-cache key. A temporary file
was atomically renamed by one process before the other process consumed it. The
successful ContractKV half-cell was discarded, both sides were reset, and every
cell was rerun with an isolated compile and Triton cache on the 8T disk. The
corrected Qwen pair and all later cells completed. This was an orchestration
race, not a model or ContractKV failure.

## Claim boundary

This is a strong same-sample cross-model result for a common qualified RULER
scope. It does not replace the all-workflow global Qwen/Mistral results, and it
does not claim that every Llama workflow is safely canonicalizable. Global and
qualified-scope rows must remain separately labeled in the paper.

## Actual result-producing code

- `scripts/run_common_ruler_cross_model.sh`
- `scripts/verify_frozen_ruler_sessions.py`
- `scripts/phase19b_end_to_end_live.py`
- `scripts/run_vllm_server.sh`
- `scripts/stop_vllm_server.sh`
- `scripts/summarize_submission_repeats.py`
- `scripts/score_common_ruler_replay.py`
- `scripts/summarize_common_ruler_cross_model.py`
- `scripts/summarize_common_ruler_quality.py`
- `scripts/install_vllm_v1_ephemeral_shadow_hook.py`
- `scripts/install_vllm_v1_prefix_metrics_probe.py`

Test files are intentionally excluded.
