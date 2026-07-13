# Phase 20 Submission Closure

## Decision

Phase 20 is complete and experiments stop at the pre-registered boundary. No third model, including the available Mistral-7B-Instruct-v0.3 checkpoint, is used as a rescue experiment.

## What closed successfully

1. Frozen Qwen outputs pass repository-standard quality and sensitivity closure. Phase 19 remains the strongest real serving evidence.
2. Llama rejections were separated into true path divergence, length stops, and one evaluator-format issue without weakening exact contracts.
3. Ephemeral candidate execution and abort behavior were source-level clean.
4. The sealed heldout evaluation was run with disjoint samples/source groups and a frozen policy.
5. The result identifies a concrete cross-model safety gap rather than hiding it.

## Code versus idea versus other causes

**Implementation issues fixed before the valid result:** finish-reason classification, structural control-echo extraction, source-hook cleanup action, cohort-by-cohort lifecycle fairness, request-ID joining, and the foreground interference comparator.

**Design limitations that remain:** Turn 0 certificates do not cover future dynamic turns; exact Tier 2 contracts recovered no development sessions; and a full candidate prefill plus separate promotion prefill costs 14.5 s at frozen p95, far outside a 3 s slack window.

**Other factors:** one violating row differed across independent processes or sat on a score boundary. The other 11 violating rows were reproducible, so randomness is not the main explanation.

## Defensible paper position

The Qwen3-8B mainline retains strong real serving results with frozen quality gates. Llama establishes that the current certificate is not universally transferable and motivates per-turn or dependency-aware recertification. Phase 20 does not claim successful two-tier promotion, universal cross-model safety, or Mistral validation.
