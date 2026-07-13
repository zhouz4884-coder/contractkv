# Phase 19 Closeout

## Decision

Phase 19 execution is complete. The evidence supports a strong Qwen3-8B
end-to-end serving result and a bounded negative cross-model result.

- Phase 19A: frozen-policy quality rebuild complete.
- Phase 19B: Qwen3-8B task-bearing live-serving gate passes.
- Phase 19C: Llama-3.1-8B evaluation completes, safety gates pass, but the
  frozen coverage and work-reduction gates fail.
- Dataset inventory: all required local archives, extracted repositories, and
  the 1,300-row unified pool are present on the 8 TB volume.

## Headline Evidence

Across Qwen3-8B concurrency 1/2/4, ContractKV reduces net mean TTFT by
35.99%/41.66%/39.56%, reduces total new-prefill work by 59.13%, and improves
1,000 ms SLO-compliant request rate by 74.86%/393.04%/539.34%. Completion is
100%, quality violations are zero, certified stable-prefix reuse is 99.98%,
and dynamic-suffix reuse is zero.

The Llama replay retains safety (zero unsafe certification and zero quality
violations) and delivers a 14.64% net TTFT reduction, but safe coverage is only
41.18%, new-prefill reduction 24.15%, and retained prefix gain 24.43%. These
miss the frozen 50%/30%/50% cross-model thresholds. This result narrows the
next research problem to verifier generalization rather than vLLM integration.

## Data Scale

The server has 1,300 unified examples: 600 LongBench, 200 RULER, and 500
RepoBench. Of these, 761 are in the live-serving partition. Phase 19B uses 50
balanced untouched sessions and 6,000 policy requests to isolate causal system
effects. This is adequate for the current systems gate, but a paper-level
full-pool or official benchmark-scoring expansion remains desirable for task
quality confidence. Data availability is not the limiting factor.

## Correctness Audit

The final results incorporate fixes for unequal cold-turn accounting, decode
length mismatch, first-chunk versus total-prefill accounting, and dynamic
suffix attribution. A prompt-logprob prefetch experiment was rejected because
it bypassed useful prefix lookup and increased total cost. A random-nonce
workload modification was also rejected because it changed certificate
coverage. Exact token LCP is used instead.

## Publication Boundary

The Qwen3-8B live-serving result is suitable as main system evidence after
full reproducibility review. The Llama result belongs in cross-model analysis
or limitations until a fresh, model-robust verifier passes the frozen gate.
None of these task-sanity results should be described as official full RULER,
LongBench, or RepoBench leaderboard scoring.
