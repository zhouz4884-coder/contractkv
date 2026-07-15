# Phase 26R: Observation-Scope Repair and Sealed-Pilot Diagnosis

## Status

Phase 26R closed the stale-certificate, weak open-QA contract, small-sample
selection, repository-context, and terminal-stop instrumentation gaps. Its v5
sealed run is retained as a calibration pilot rather than paper evidence: it
exposed two further boundaries that required a fresh Phase 26S protocol.

## What Was Repaired

- A certificate is bound to one observation identity and epoch. Future turns
  are never authorized by a Turn-0 decision.
- Open-QA lexical F1 is diagnostic-only and can never publish cache state.
- RepoBench uses the same frozen repository context and contract hash during
  audit and deployment.
- Typed qualification uses Wilson confidence and has no global coverage quota.
- vLLM exports a terminal-stop margin and the verifier requires a positive
  stop reserve.
- Cache salts isolate verifier publications between observations while raw
  fallback retains native vLLM APC.

## Sealed-v5 Finding

The first complete Exact-only cell contained 500 observations. Two RepoBench
observations from the same session passed the compact teacher-forced check but
an independent TP=2 greedy decode followed a different path and stopped by
length. Both false-safe cases had candidate-margin q05 near `1.075`; they were
real output differences, not scoring artifacts.

The same pilot also showed a design-level economics problem. With 6000 ms
declared tool slack, mean unhidden verification cost was about 193 ms for
RULER, 1.64--2.68 s for LongBench families, and 9.93 s for RepoBench. Paying
that cost for every observation erased the serving benefit.

Machine-readable evidence is in
`results/cross_model/deepseek_phase26r_scope_closure/pilot_failure_diagnosis_v5.json`.

## Root-Cause Classification

The false-safe was an implementation/protocol robustness issue: a candidate
margin threshold of 1.0 was insufficient to transfer a teacher-forced result
to a separate DeepSeek TP=2 decode. The negative net TTFT was a design issue:
observation-scoped safety forbids amortizing verification across future turns,
so expensive families must be rejected before verification. Neither issue is
fixed by relaxing lexical contracts or by reporting the offline oracle.

## Disposition

The v5 split was opened by this diagnosis and is excluded from formal results.
Phase 26S freezes the numerical and economic corrections from v5, then uses a
new v6 split with zero sample-ID overlap with v1--v5.
