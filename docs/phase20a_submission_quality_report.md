# Phase 20A: Frozen Quality and Sensitivity Closure

## Scope

Phase 20A rescored existing Phase 19 outputs without regenerating responses or changing policy decisions. Repository-standard task scorers were applied to 734 Phase 19A pairs (692 scorable) and 1,350 Phase 19B ContractKV pairs. References were used only after serving and never entered admission.

## Frozen-input checks

- Candidate identity unchanged: pass.
- Policy hash unchanged: pass.
- Material official-score drop absent: pass.
- Unsafe certified sessions: zero.
- Overall gate: pass.

Held-out candidate-minus-raw mean score deltas were -0.001253 for HotpotQA, -0.006811 for NarrativeQA, -0.004412 for Qasper, 0 for RULER, and +0.000422 for RepoBench. ContractKV-effective held-out outputs had zero delta because unsafe candidates remained on the raw path.

## Serving sensitivity

At a 1,000 ms SLO, the Qwen3-8B Phase 19B replay showed 1.749x, 4.930x, and 6.393x SLO-compliant request-rate gains in low, transition, and saturation regimes. These are frozen-output serving measurements, not a new generation run.

At 2 s tool slack, net TTFT reduction was 35.99%, 41.66%, and 39.56% in the same three regimes. The complete SLO and slack sweeps are retained in machine-readable CSV files.

## Claim boundary

Phase 20A closes scoring and sensitivity reporting for the frozen Qwen evidence. It does not establish cross-model generalization or validate the Phase 20 two-tier promotion protocol.
