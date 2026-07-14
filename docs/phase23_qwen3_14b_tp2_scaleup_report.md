# Phase 23: Qwen3-14B TP=2 Scale-Up

## Goal and Frozen Protocol

This limited scale-up tests whether the Qwen3-8B ContractKV control path remains effective for a larger Qwen model under tighter per-GPU memory.

- Model: Qwen3-14B, eight complete safetensor shards (28 GiB on disk)
- Hardware: 2 x RTX 3090, tensor parallel size 2
- Runtime: vLLM 0.10.2 with the existing source-level verifier and prefix metrics hooks
- Workload: 25 frozen sessions, five each from RULER, HotpotQA, NarrativeQA, Qasper, and RepoBench
- Sessions: 10 turns, 225 measured future requests per policy per repeat
- Policies: raw order and `contractkv-full`
- Load: concurrency 2, `max_num_seqs=2`, `max_model_len=8192`
- Generation: float16, temperature 0, 96 output tokens maximum
- Repeats: three fresh raw/ContractKV process pairs with order raw-contract, contract-raw, raw-contract

The 25 sessions have zero sample overlap and zero source-group overlap with prior ContractKV experiments. The Qwen3-8B architecture policy is transferred without 14B-specific threshold tuning; every promoted session must pass a Qwen3-14B-local Turn-0 verifier.

## Aggregate Result

| Metric | Raw | ContractKV | Change |
|---|---:|---:|---:|
| Completion | 100% | 100% | equal |
| Mean TTFT | 2005.78 ms | 854.99 ms observed | -57.37% observed |
| Net mean TTFT | 2005.78 ms | 1109.20 ms | **-44.69%** |
| p95 TTFT | 3938.07 ms | 2751.81 ms | **-30.12%** |
| Mean new-prefill | 3408.80 tokens | 1344.09 tokens | **-60.57%** |
| SLO-compliant req/s (2000 ms) | 0.306 | 0.893 | +191.55% |
| Certificate coverage | n/a | 68% | 17/25 sessions |
| Certified prefix physical reuse | n/a | 99.9725% | pass |
| Mean reused physical blocks | n/a | 195.07 | measured |
| Peak request physical blocks | n/a | 470 | measured |
| Dynamic suffix reuse | n/a | 0 tokens | pass |
| Policy-attributable quality violations | n/a | 0 / 675 pairs | pass |

Net TTFT includes verifier time not hidden by the frozen 2000 ms tool-slack budget. It is the paper-facing latency metric.

## Repeat Stability

| Repeat | Net mean TTFT reduction | p95 reduction | New-prefill reduction | Certificate coverage | Physical reuse |
|---:|---:|---:|---:|---:|---:|
| 1 | 42.59% | 30.20% | 60.57% | 68% | 99.9725% |
| 2 | 46.94% | 30.30% | 60.57% | 68% | 99.9725% |
| 3 | 44.54% | 29.87% | 60.57% | 68% | 99.9725% |

The reverse-order second repeat is the strongest rather than the weakest result, so the benefit is not explained by ContractKV always running after raw.

## Quality and Fail-Closed Behavior

All five task families preserve the raw task-sanity score in every repeat. Promotion fractions are 40% for HotpotQA, 60% for NarrativeQA, 60% for Qasper, 100% for RULER, and 80% for RepoBench. No promoted pair exceeds the 0.03 quality-drop budget.

Each repeat has 17 verifier passes, 7 verifier failures, and one incomplete Qasper canary. The incomplete case ends by length at the frozen 96-token output budget. ContractKV aborts its speculative certificate and serves all future turns in raw order. Future completion remains 100%. This is correct fail-closed behavior and was not repaired by changing the frozen output budget.

## Interpretation

The 14B result strengthens both scale and causal attribution:

1. The token-side reduction (60.57%) closely matches the established Qwen3-8B mechanism, so the millisecond improvement is not merely a larger model making all prefill slower.
2. Scheduler-observed physical reuse is nearly exact and dynamic-suffix reuse remains zero, tying the speedup to certified stable-prefix reuse.
3. The net mean and p95 improvements survive three complete fresh-process pairs and execution-order reversal.
4. The larger model uses approximately 21.8 GiB per GPU during replay, yet completes every future request at concurrency 2.

This supports a limited scale-up claim: ContractKV generalizes from Qwen3-8B to Qwen3-14B under TP=2 for the frozen five-family workload. It is not a complete five-task x four-policy x three-load capacity matrix, and task quality is task-sanity scoring rather than official full benchmark scoring.

## Evidence and Code

- `results/scale_up/qwen3_14b_tp2_v0/repeat_summary_v0.csv`
- `results/scale_up/qwen3_14b_tp2_v0/aggregate_summary_v0.csv`
- `results/scale_up/qwen3_14b_tp2_v0/family_quality_v0.csv`
- `results/scale_up/qwen3_14b_tp2_v0/quality_pairs_v0.csv`
- `results/scale_up/qwen3_14b_tp2_v0/gate_v0.json`
- `results/scale_up/qwen3_14b_tp2_v0/split_commitment_v0.json`
- `results/scale_up/qwen3_14b_tp2_v0/policy_transfer_manifest_v0.json`
- `scripts/phase23_prepare_qwen14_scaleup.py`
- `scripts/run_phase23_qwen14_scaleup.sh`
- `scripts/phase19b_end_to_end_live.py`
- `scripts/phase23_qwen14_scaleup_analysis.py`
- `scripts/run_vllm_server.sh`
- `scripts/stop_vllm_server.sh`
- `scripts/install_vllm_v1_ephemeral_shadow_hook.py`
- `scripts/install_vllm_v1_prefix_metrics_probe.py`
