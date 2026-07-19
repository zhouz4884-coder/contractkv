# P0-A Service-Template Formal Task-Quality Audit

## Protocol

Five semantically coherent deployed templates (RULER, HotpotQA, NarrativeQA, Qasper, and RepoBench) are each consumed by ten authorized tenants for ten turns. D0 raw order and D2 template-certificate cells use three paired fresh processes. Each tenant receives the same template-consistent context, query, and answer; only a neutral private tool-observation identity changes. Generation uses the frozen task budgets rather than the 64-token marker budget.

| Family | Paired future outputs | Raw score | D2 score | Paired delta (95% cluster CI) | Violations >0.03 | Raw fallback |
|---|---:|---:|---:|---:|---:|---:|
| ALL | 1350 | 0.356000 | 0.356000 | +0.000000 [+0.000000, +0.000000] | 0 | 20.00% |
| HotpotQA | 270 | 0.500000 | 0.500000 | +0.000000 [+0.000000, +0.000000] | 0 | 0.00% |
| NarrativeQA | 270 | 0.000000 | 0.000000 | +0.000000 [+0.000000, +0.000000] | 0 | 0.00% |
| Qasper | 270 | 0.200000 | 0.200000 | +0.000000 [+0.000000, +0.000000] | 0 | 100.00% |
| RULER | 270 | 1.000000 | 1.000000 | +0.000000 [+0.000000, +0.000000] | 0 | 0.00% |
| RepoBench | 270 | 0.080000 | 0.080000 | +0.000000 [+0.000000, +0.000000] | 0 | 0.00% |

## Safety gate

Overall gate: **PASS**. Paired future outputs: 1350; completion 100%: True; policy quality violations zero: True; scope-invalid admissions zero: True; unauthorized reuse zero: True.

The hierarchical bootstrap resamples fresh process, service template, and tenant session. This closes certificate fan-out for four qualified templates and fail-closed behavior across all five; it does not replace the broader frozen full-task quality experiments.

## Fail-closed negative control

The archived policy that issued certificates to all five templates produced 3 paired metric drops. All were Qasper: True. The pre-existing Qasper risk qualification therefore remains raw-order; the paper-facing guarded policy eliminates those drops: True. The archived rows remain machine-readable and are not counted as successful ContractKV admissions.
