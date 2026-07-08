# Phase 6D Runtime Replay Report

## Goal

Replay `ContractKV-Indep` and `ContractKV-Joint` through the Python runtime wrapper on the same 140 unified samples.

Output:

- `results/runtime/runtime_replay_policy_eval_v0.csv`

## Results

Rows: 280.

| Policy | Admission | Mean risk | Mean memory saving MB | Mean controller overhead ms |
| --- | ---: | ---: | ---: | ---: |
| ContractKV-Indep | 0.000 | 0.066105 | 283.093 | 0.037 |
| ContractKV-Joint | 1.000 | 0.005386 | 53.309 | 0.137 |

## Interpretation

`ContractKV-Indep` remains too aggressive in replay: it saves more memory but violates the quality budget. `ContractKV-Joint` uses the same runtime path and lowers risk enough to admit all traces under the Phase 6 replay budget.

The runtime replay confirms that the Phase 5 decision logic can be loaded and executed inside a Python serving-path wrapper with sub-millisecond controller overhead.

## Timing Source

`vllm_observed_ttft_ms` and `vllm_observed_tpot_ms` are Phase 2 reference timing estimates for replay-scale analysis. Fresh live vLLM forwarding is validated by the Phase 6A smoke table.

## Boundary

This replay does not claim real KV goodput or real cache placement. It validates runtime integration, decision consistency, and transfer proxy accounting.
