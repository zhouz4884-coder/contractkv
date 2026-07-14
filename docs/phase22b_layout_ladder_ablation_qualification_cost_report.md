# Phase 22B: Layout Ladder Ablation and Qualification Cost

## Scope

This report uses the completed Llama-3.1-8B development cells and sealed held-out replay. It does not rerun or tune on held-out outputs. The four development policies are:

1. `fixed_L3`: request L3 for every family, with the existing Turn-0 verifier still allowed to fail closed.
2. `family_fixed_maximum`: use the prospectively frozen maximum level for each family, without lower-level recovery.
3. `certificate_guided_descent`: try only preregistered eligible levels at or below the family maximum, then fall back to L0.
4. `raw_fallback`: use L0 for every session.

Future-turn quality is used only to evaluate safety after selection. It is never used to choose a session's level.

## Development Ablation

| Strategy | Completion | Promoted coverage | Safe completed coverage | Policy quality violations | Retained prefix gain | New-prefill reduction |
|---|---:|---:|---:|---:|---:|---:|
| fixed L3 | 100% | 64% | 56% | 10 | 1215.50 tokens | 48.98% |
| family-fixed maximum | 100% | 52% | 52% | 0 | 816.36 tokens | 32.90% |
| certificate-guided descent | 100% | 52% | 52% | 0 | 816.36 tokens | 32.90% |
| raw fallback | 100% | 0% | 0% | 0 | 0 | 0% |

The development data reject the strongest version of the ablation hypothesis. Absolute completion is already 100% for all four policies, and no L1 certificate recovers a development session rejected at its family maximum. Descent therefore does not improve completion, safe coverage, or retained prefix gain in these 25 sessions.

The safety result is still decisive: compared with fixed L3, certificate-guided descent removes all 10 policy-attributable future quality violations and both unsafe promoted sessions. Fixed L3 obtains more reuse by admitting layouts that violate the frozen quality budget; its larger prefix gain is not a safe systems win.

## Sealed Held-Out Check

The 50-session, three-fresh-pair held-out replay contains one NarrativeQA session whose L2 certificate fails but L1 passes. Replacing descent with direct raw fallback for that session yields:

| Strategy | Completion | Safe completed coverage | Quality violations | Retained prefix gain | New-prefill reduction |
|---|---:|---:|---:|---:|---:|
| family-fixed maximum | 100% | 48% | 0 | 721.39 tokens | 30.41% |
| certificate-guided descent | 100% | 50% | 0 | 734.79 tokens | 30.97% |
| raw fallback | 100% | 0% | 0 | 0 | 0% |

Thus descent has a small but real held-out benefit: it preserves the 100% completion ceiling, raises safe completed coverage by 2 percentage points, and adds 13.40 retained prefix tokens per request without a quality violation. The paper should claim safety-preserving coverage recovery, not universal completion improvement.

## Qualification Cost

| Item | Measured value |
|---|---:|
| Development sessions | 25 (5 per family) |
| Ladder cells | 4 |
| Measured wall time | 645.44 s |
| GPUs | 2 x RTX 3090 |
| GPU-hours | 0.3586 |
| Frozen manifest size | 1,678 bytes |
| Runtime family/level lookup mean | 0.125 us |
| Runtime family/level lookup p95 | 0.200 us |

GPU-hours are measured wall time multiplied by the two concurrently occupied GPUs. They exclude model download and include the four live ladder cells executed in two parallel waves.

Exact development-subset enumeration gives the following prospective selection stability:

| Family | Frozen level | Samples for >=80% stable selection | Samples for 100% stable selection |
|---|---:|---:|---:|
| HotpotQA | L2 | 3 | 4 |
| NarrativeQA | L2 | 4 | 5 |
| Qasper | L0 | 4 | 5 |
| RULER | L3 | 1 | 1 |
| RepoBench | L0 | 1 | 1 |

Five sessions per family are sufficient to reproduce every final decision in this development split. Harder QA families consume the full conservative budget; obvious positive and fail-closed families stabilize earlier.

## Paper Claim

New-model qualification is lightweight in this setup: 0.36 GPU-hours, a 1.6 KiB manifest, and sub-microsecond runtime lookup. The ladder's primary value is not raising an already saturated request completion rate. It prevents unsafe high-reuse layouts and can recover additional safe coverage when a lower certified level remains valid.

## Evidence and Code

- `results/cross_model/llama_broad_generalization_r3/layout_ladder_ablation_v0.csv`
- `results/cross_model/llama_broad_generalization_r3/layout_ladder_heldout_descent_ablation_v0.csv`
- `results/cross_model/llama_broad_generalization_r3/qualification_cost_v0.csv`
- `results/cross_model/llama_broad_generalization_r3/qualification_sample_stability_v0.csv`
- `scripts/phase23_layout_ablation_qualification_cost.py`

Claim boundary: the development ablation composes real isolated ladder cells; the held-out descent comparison composes already executed raw and certified cells. Neither is a new live serving run.
