# Phase 14R-C Physical Prefix Residency Validator

## Result

The read-only V1 validator passed its implementation gate on Qwen3-8B with vLLM 0.10.2. It reuses vLLM's native request block hashes and compares the cache-hit decision made before allocation with the post-allocation request block table.

| Metric | Result | Gate |
| --- | ---: | ---: |
| Requests | 20 | nonzero |
| Within one physical block | 20/20 | >=95% |
| Residency mispredictions | 0 | <5% |
| Mean probe overhead | 0.017 ms | diagnostic |
| p95 probe overhead | 0.024 ms | <0.2 ms |

The first implementation redundantly scanned every cached hash and cost roughly 2.3 ms for a 376-block prefix. The final hook records the native longest-hit result already produced by vLLM and validates after allocation; it does not pin blocks or alter replacement behavior.

## Scope

The validator establishes physical cache facts at the scheduler boundary: native block hashes, cached hit length, physical block IDs, refcounts, and allocation-time agreement. It does not claim an externally atomic reservation: a concurrent eviction after the scheduling decision remains a possible race and is represented by the cache epoch/misprediction path.

## Artifacts

- `scripts/install_vllm_v1_residency_validator.py`
- `scripts/install_vllm_v1_prefix_metrics_probe.py`
- `scripts/summarize_vllm_residency_validator.py`
- `results/hard_systems/phase14rc_residency_raw_v2.csv`
- `results/hard_systems/phase14rc_residency_summary_v2.csv`
