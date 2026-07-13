# Phase 19C: Llama Cross-Model Replay

## Scope

Phase 19C tests whether the frozen transactional protocol transfers from
Qwen3-8B to Llama-3.1-8B-Instruct. It uses a model-specific calibration split
of 10 sessions and a disjoint held-out split of 20 sessions, with no overlap
with Phase 19B. The held-out live replay covers four policies, ten turns, and
800 rows (80 unmeasured initialization rows and 720 measured future requests).

The final policy binds the model revision, tokenizer, chat template, vLLM
version, decode configuration, calibration labels, and terminal protocol under
policy hash `e6497794e4eaf6f5f464dcadbddf91dcf4d469f72d932ad6879eac91a27a7265`.
No held-out threshold retuning is allowed.

## Result

The evaluation completed, but the strict cross-model performance gate did not
pass. Transactional correctness and safety transfer; coverage and work-saving
strength do not meet the frozen thresholds.

| Metric | Result | Gate |
| --- | ---: | ---: |
| Completion | 100% | pass |
| Unsafe sessions certified | 0 / 3 | pass |
| Quality violations | 0% | pass |
| Certified stable-prefix reuse | 99.96% | pass (>=95%) |
| Dynamic-suffix reuse | 0 tokens | pass |
| Safe-session certificate coverage | 7 / 17 = 41.18% | fail (>=50%) |
| Net TTFT reduction | 14.64% | pass for diagnostic zero floor |
| New-prefill reduction | 24.15% | fail (>=30%) |
| Retained available prefix gain | 24.43% | fail (>=50%) |

At concurrency 2, raw-order mean TTFT is 1293.31 ms and ContractKV observed
mean TTFT is 1000.70 ms. Charging 103.31 ms unhidden verifier cost per future
request gives 1104.01 ms net TTFT, a 14.64% reduction. The 1,000 ms SLO-compliant
request rate rises from 0.349 to 0.512 req/s (46.71%). These are positive
signals, but they do not override the failed frozen work-reduction gates.

## Root Cause

This is no longer explained by the implementation defects found in Phase 19B:
cold-turn alignment, decode length, total-prefill accounting, and exact-LCP
dynamic-reuse accounting are all fixed in this replay. The remaining failure
is a policy-generalization limitation. Same-backend strict top-1 verification
is fail-closed on Llama and certifies only 7 of 17 empirically safe held-out
sessions. It therefore falls back often enough to retain only 24.43% of the
available physical prefix gain.

The policy-bound calibration summary used the earlier first-chunk diagnostic.
After the total-prefill correction, a separate non-policy-mutating audit gives
27.43% retained prefix gain on calibration. It is retained as
`phase19c_calibration_quality_summary_corrected_v1.json`; the original bound
files are not overwritten because that would invalidate the frozen policy
hash after held-out execution.

## Claim Boundary

Phase 19C establishes cross-model transaction integrity, fail-closed safety,
and real prefix reuse when certified. It does not establish a strong
cross-model performance result. The next algorithmic step is a model-robust
verifier or calibrated acceptance rule evaluated on a fresh split, not a
post-hoc relaxation of this held-out gate.

## Actual Code Used

- `scripts/phase19c_prepare_cross_model.py`
- `scripts/phase19c_freeze_quality_labels.py`
- `scripts/phase19c_finalize_model_policy.py`
- `scripts/run_phase19c.sh`
- `scripts/phase19b_end_to_end_live.py`
- `scripts/phase19b_summarize_net_benefit.py`
- `scripts/install_vllm_v1_prefix_metrics_probe.py`
- `scripts/run_vllm_server.sh`
- `scripts/stop_vllm_server.sh`

## Evidence

- `results/cross_model/phase19c_frozen_policy_v0.json`
- `results/cross_model/phase19c_task_replay_raw_v0.jsonl`
- `results/cross_model/phase19c_summary_v0.csv`
- `results/cross_model/phase19c_gate_v0.json`
- `results/cross_model/phase19c_heldout_quality_labels_v0.csv`
- `results/cross_model/phase19c_heldout_quality_summary_v0.json`
- `results/cross_model/phase19c_calibration_quality_summary_corrected_v1.json`
