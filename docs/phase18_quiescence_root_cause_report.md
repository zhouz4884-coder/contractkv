# Phase 18A: Quiescence Root-Cause Screening

## Scope

Phase 17R established that Qwen3-8B exceeded the fixed 10 ms p95 foreground-interference budget. This record separates confirmed implementation defects from remaining system behavior. Frozen verifier policy, transaction semantics, and quality results were not changed.

## Confirmed Code Defects

1. The original `32` token limit applied per shadow request. Two shadow requests could therefore execute 64 aggregate tokens in one scheduler round. The hook now enforces `CONTRACTKV_SHADOW_ROUND_TOKENS=32`; the corrected 8B event trace observed 1,207 shadow rounds with maximum aggregate work exactly 32 tokens.
2. The first global-budget patch returned zero granted tokens for ordinary non-shadow requests, triggering vLLM's `assert num_new_tokens > 0`. The grant function now returns `None` for non-shadow requests. This was a hook-boundary code error, not a model or scheduling limitation.

## C0/C1 Live Screening

Both cells use Qwen3-8B, global 32-token cap, 10 ms idle grace, 1--8 ms backoff, 60 baseline foreground requests, 60 live foreground requests, and six verifier requests.

| Cell | Tracing | p95 foreground penalty | Foreground | Verifier |
| --- | --- | ---: | --- | --- |
| C0 | synchronous JSONL event output | 19.51 ms | 60/60 | 6/6 |
| C1 | no critical-path file I/O | 15.12 ms | 60/60 | 6/6 |

Removing synchronous event writes reduces the observed penalty by 4.40 ms across these separate trials, establishing that critical-path I/O contributes material control-plane interference. It does not establish the exact causal magnitude because the trials are not paired and per-seed jitter remains high.

## Current Root-Cause Status

The residual C1 penalty still exceeds 10 ms. At this point it cannot honestly be attributed solely to GPU non-preemption: polling gates, full prompt-logprob egress/JSON serialization, and request queueing are still present. Therefore Phase 18's full closure gate remains open.

The next required implementation steps are event-driven shadow parking, compact EngineCore-to-frontend verifier egress, and one-shot collision/CUDA-event timing. Only if that cleaned path still exceeds 10 ms should a frozen wall-time LUT be introduced.

## Claim Boundary

The result supports: synchronous JSONL logging is avoidable overhead, and a per-request token cap was an implementation bug. It does not yet support: a physical non-preemption lower bound, a production-safe static 10 ms verifier configuration, or a wall-time policy evaluation.
