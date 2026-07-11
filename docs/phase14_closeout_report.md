# Phase 14 Closeout

## What Is Now Established

1. CAPOSC can be tied to real vLLM V1 physical cache facts with negligible read-only overhead.
2. In shared-context agent serving, legal canonical layouts turn repeated logical prefixes into shared physical KV blocks and substantially reduce real TTFT, scheduler wait, and block-pool pressure.
3. Cold fan-out has a measurable cache-fill race; singleflight priming resolves it.
4. The static request-level quality selector remains closed. Teacher-forced SLC is a high-precision fail-closed guard but does not yet have deployable coverage.
5. The open-loop endpoint evaluation shows a large sustainable CAPOSC operating region and correctly rejects short-window false knees.

## Paper Position

The strongest current paper claim is a real vLLM system result: segment contracts and cache-aware canonical layout create cross-session physical prefix reuse under legal ordering constraints. This reduces actual prefill work and KV block pressure, yielding strong low- and high-load endpoint performance on shared-context agent serving.

Do not claim universal safe automatic canonicalization. The evidence instead supports a two-plane framing: CAPOSC is the performance compiler; SLC/QC are fail-closed safety mechanisms whose coverage remains an open deployment limitation.

## Next Required Experiment

Run a longer raw-order open-loop measurement at lower offered rates until an all-seed stable raw knee has enough completions, then repeat the same protocol on a natural mixed-agent workload. That will turn the current capacity separation into a final paper-grade capacity-lift ratio.
