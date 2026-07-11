# Phase 16R-B: In-Situ Verifier

## Objective

Phase 16R-B turns the same-backend smoke test into an independent verifier node.
It consumes a `RawAttestation`, candidate `prompt_logprobs`, and fixed thresholds,
then returns a `VerifyReport`. It does not mutate cache state or invoke PSTP.

## Evidence Path

- Raw token IDs come from the vLLM generation response. Output text is never
  retokenized to reconstruct the answer path.
- Raw margins use generation top-2 logprobs and the strongest non-target token.
- Candidate verification uses an integer-token completion prompt and
  `prompt_logprobs=2` on the same vLLM backend.
- Missing target/competitor/rank, a length stop, missing stop metadata, or an
  inconsistent candidate stop produces `INCOMPLETE`.
- The decision uses top-1 path equality, stop consistency, q05 raw/candidate
  margins, q95 margin degradation, and a robustness reserve.
- Both raw and teacher-forced requests use `CANCELLED` PSTP specs, so verifier
  work cannot publish cache entries.

## Live Result

On Qwen3-4B, 12 safe reordering cases passed. Their robustness reserve ranged
from 2.940 to 3.426 (mean 3.217). Mean raw q05 margin was 9.709, mean candidate
q05 margin was 9.454, and mean q95 degradation was 0.783. The measured end-to-end
verification request time averaged 756.2 ms; this includes vLLM request execution
and is not controller CPU overhead.

Four deliberately conflicting candidates returned `INCOMPLETE` because the
required candidate stop token was not top-1. They were rejected rather than
silently certified. The target-absent and strongest-competitor fail-closed paths
are additionally covered by deterministic interface tests.

## Historical False-Safe Diagnosis

The two Phase 15 false-safe cases were not top-1 or stop failures:

| Task/sample | Quality drop | Token path | Minimum margin | Stop | Classification |
|---|---:|---:|---:|---:|---|
| qasper/58 | 0.031358 | 1.0 | 0.78125 | consistent | low-margin false-safe candidate |
| narrativeqa/165 | 0.050420 | 1.0 | 0.03125 | consistent | low-margin false-safe candidate |

This classification identifies the missing evidence dimension; it does not claim
that the current reserve threshold has already rejected both cases. Thresholds
must be calibrated against a larger paired quality set rather than tuned to two
examples.

Evidence:

- `results/hard_systems/phase16r_verifier_live_v0.csv`
- `results/hard_systems/phase16r_historical_false_safe_classification_v0.csv`

## Claim Boundary

The node is decision-ready for same-backend greedy token-path verification. It is
not a semantic equivalence proof, a future-turn certificate, or an automatically
connected cache actuator.
