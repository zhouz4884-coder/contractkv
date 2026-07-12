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

### C2 parking result

The corrected parked-shadow implementation counts parked requests as unfinished EngineCore work, performs exactly one waiting-queue pop, and wakes through normal admission while preserving `num_computed_tokens`. A Qwen3-8B live regression completed 60/60 foreground and 6/6 verifier requests without a hang. Its pooled p95 penalty was 15.92 ms, compared with 15.12 ms for C1. Given the large seed spread (-0.65 to +33.61 ms), this does not show a latency improvement. It does show that repeated polling was not the dominant residual in this workload.

### C3/C4 source-level compact result

The earlier architectural blocker is closed with a vLLM 0.10.2 source branch.
The implementation extends the existing EngineCore request/output schema and
routes compact verifier results in `AsyncLLM`; it does not add a second transport.
Normal API regression succeeded for 200/200 valid requests, sequential compact
verification succeeded for 100/100 requests, and concurrent compact verification
succeeded for 20/20 requests.

Five fresh Qwen3-8B seeds produced pooled p95 foreground deltas of -4.80 ms for
C3 polling and -3.37 ms for C4 parking. Each cell completed 500/500 live
foreground requests and 20/20 verifiers with zero pending futures or orphan
outputs. The full prompt-logprob HTTP response was 831,262 bytes, compared with
387 mean compact bytes; the maximum compact EngineCore wire object was 231 bytes.

Per-seed tail jitter remains substantial, so the negative pooled values are not
claimed as acceleration. They do establish that the earlier systematic
full-egress residual is absent. The detailed result and claim boundary are in
`docs/phase18_compact_egress_report.md`.

## Claim Boundary

The result supports: synchronous JSONL logging is avoidable overhead; a global
round budget is required; event-driven parking is lifecycle-correct; and compact
source-level egress removes bulk prompt-logprob transport from the verifier path.
It does not support: deterministic improvement in every seed, parking as an
independent latency optimization, a physical non-preemption lower bound, or a
wall-time LUT. CUDA collision timing is deferred because the cleaned pooled C3/C4
path does not retain a systematic penalty above 10 ms.
