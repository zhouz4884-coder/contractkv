# Phase 10.5D Recompute Quality Report

## Goal

Verify that RAR-exact releases KV residency rather than semantic content.

Quality policies:

```text
vLLM-default
full-recompute
ContractKV-RAR-exact
eviction/truncation reference
```

## Outputs

```text
results/hard_systems/contractkv_recompute_quality_raw_v0.csv
results/hard_systems/contractkv_recompute_quality_eval_v0.csv
```

## Results

| Policy | Dataset | Mean Score | Quality Drop | Close To Default |
| --- | --- | ---: | ---: | --- |
| vLLM-default | phase10_5_long_probe | 1.000000 | 0.000000 | true |
| full-recompute | phase10_5_long_probe | 1.000000 | 0.000000 | true |
| ContractKV-RAR-exact | phase10_5_long_probe | 1.000000 | 0.000000 | true |
| eviction-truncation | phase10_2_real_matrix | 0.737873 | 0.262127 | false |
| context-truncation | phase10_2_real_matrix | 0.883245 | 0.116755 | false |

## Interpretation

On the exact-recompute probe, all three non-deletion policies returned the expected `OK` answer:

```text
vLLM-default ~= full-recompute ~= ContractKV-RAR-exact
```

The deletion references remain harmful under the real Phase 10.2 Qwen3-8B quality matrix:

```text
segment eviction mean drop = 0.262127
context truncation mean drop = 0.116755
```

This supports the intended distinction:

```text
ContractKV releases KV residency, not semantic content.
```

## Boundary

This is a tier0 quality sanity check. It proves that the RAR-exact actuator can preserve output on the long probe. It does not replace a full 140-trace quality replay, which should follow the larger Phase 10.5C pressure run.
