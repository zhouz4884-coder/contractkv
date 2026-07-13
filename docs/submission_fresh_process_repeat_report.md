# Submission Fresh-Process Repeat Report

## Protocol

Qwen3-8B and Mistral-7B-Instruct-v0.3 each run raw-order and ContractKV at
concurrency two. Every model-policy cell has three independent vLLM server
processes. GPU assignment alternates, repeat 2 reverses launch order, turn 0 is
unmeasured, and all summaries use identical future-turn keys. Net mean TTFT
charges verification time outside the frozen 2,000 ms tool-slack window.

## Results

| Model | Net mean TTFT reduction (bootstrap 95% CI) | p95 TTFT reduction | New-prefill reduction | SLO-goodput gain | Scope-invalid admitted |
|---|---:|---:|---:|---:|---:|
| Qwen | 37.81% [36.95%, 38.33%] | 33.03% | 59.13% | 183.24% | 0 |
| Mistral | 31.72% [31.36%, 32.21%] | -0.20% | 39.46% | 26.08% | 0 |

The bootstrap interval is a deterministic 10,000-resample interval over three
paired process repeats. The report also retains the full cross-run range in
`submission_repeat_aggregate_v0.csv`. Scope-invalid certificates may only
appear as raw-order fallbacks; the `scope_invalid_admitted_requests` count must
remain zero.
