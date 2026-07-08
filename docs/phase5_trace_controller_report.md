# Phase 5 Trace-Level Controller Report

## Goal

Phase 5 evaluates whether ContractKV's trace-level joint controller can choose segment lifecycle actions under quality, latency, and memory constraints better than independent baseline policies.

This phase is trace-level policy evaluation. It is not yet a vLLM-integrated runtime.

## Inputs

- Dataset samples: 140 unified samples
- Risk ledger records: 1080 proxy records
- Risk summary: `results/risk_ledger/quality_risk_summary_v0.csv`
- Cost table: `results/cost/segment_action_cost_table_v0.csv`
- Cost sources: Phase 2.5 actual context scaling, Phase 2.6 H2D/D2H transfer, and copy/decode interference proxy

## Policies

Seven policies are evaluated:

- Full-Recompute
- Prefix-Reuse-Only
- Quantization-Only
- Offload-Only
- Repair-Only
- ContractKV-Indep
- ContractKV-Joint

`ContractKV-Indep` applies locally attractive reuse, precision, placement, and prefetch choices independently. `ContractKV-Joint` solves the trace under shared quality and SLO budgets.

## Constraints

Quality budgets:

- 0.01
- 0.02
- 0.05

SLO budgets:

- 100 ms
- 200 ms
- 500 ms

## Results

The evaluation produced:

- `results/controller/cslo_decisions_v0.jsonl`
- `results/controller/trace_policy_decisions_v0.jsonl`
- `results/controller/trace_policy_eval_v0.csv`

At quality budget 0.02 and SLO 200 ms:

| Dataset | Policy | Admission | Mean latency ms | Mean risk | Memory saving MB | Quality violation | SLO violation |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| RULER | ContractKV-Indep | 0.00 | 13.967 | 0.063540 | 31.665 | 1.00 | 0.00 |
| RULER | ContractKV-Joint | 1.00 | 21.495 | 0.006432 | 26.346 | 0.00 | 0.00 |
| LongBench | ContractKV-Indep | 0.00 | 160.526 | 0.065817 | 383.325 | 1.00 | 0.33 |
| LongBench | ContractKV-Joint | 1.00 | 77.557 | 0.003787 | 63.754 | 0.00 | 0.00 |
| RepoBench | ContractKV-Indep | 0.00 | 14.370 | 0.070112 | 33.362 | 1.00 | 0.00 |
| RepoBench | ContractKV-Joint | 1.00 | 22.438 | 0.012331 | 28.050 | 0.00 | 0.00 |

Across all datasets:

| Quality budget | SLO ms | Joint avg admission | Indep avg admission | Joint win rate over Indep |
| ---: | ---: | ---: | ---: | ---: |
| 0.01 | 100 | 0.983 | 0.000 | 1.000 |
| 0.01 | 200 | 1.000 | 0.000 | 1.000 |
| 0.01 | 500 | 1.000 | 0.000 | 1.000 |
| 0.02 | 100 | 0.983 | 0.000 | 1.000 |
| 0.02 | 200 | 1.000 | 0.000 | 1.000 |
| 0.02 | 500 | 1.000 | 0.000 | 1.000 |
| 0.05 | 100 | 0.813 | 0.000 | 1.000 |
| 0.05 | 200 | 0.890 | 0.000 | 1.000 |
| 0.05 | 500 | 0.983 | 0.000 | 1.000 |

## Key Findings

ContractKV-Indep over-optimizes memory and applies the aggressive proxy quantization/offload plan without checking shared quality and latency budgets. In this v0 trace model, it consistently violates the quality budget and sometimes violates SLO as well.

ContractKV-Joint admits traces by upgrading high-risk or high-latency segment decisions until the shared constraints are satisfied. It preserves memory savings where budget permits, but avoids the full risk blow-up of the independent serial policy.

This completes the characterization-to-controller loop: dataset segments, risk estimates, hardware cost estimates, and trace-level policy decisions are now connected by machine-readable artifacts.

## Limitations

The risk table is proxy-based and should not be interpreted as real KV quantization quality. The cost table is also a trace-level proxy derived from measured latency and transfer signals, not direct vLLM kernel instrumentation.

Phase 5 does not modify vLLM, FlashAttention, RoPE, or real KV precision kernels.

## Next Phase

Phase 6 should move from trace-level validation to a Python-level vLLM ContractKV controller prototype with segment parsing, placement decision proxy, and host prefetch/offload timing simulation.
