# Phase 14D Full-Pool Workload Manifest Report

## Purpose

Phase 14D needs a larger paper-facing workload pool before running large-scale
live serving. This step builds the disjoint calibration, held-out quality, and
live-serving partitions from locally cached datasets on the 8T server disk.

This is a workload construction and audit step. It does not claim live vLLM
goodput, prefix-cache hit rate, or task-quality results.

## Server Location

Workspace:

```text
/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv
```

8T dataset/cache root:

```text
/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/datasets/contractkv_datasets/hf_cache
```

Generated full pool:

```text
/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv/results/workload/phase14d_full_pool_v0.jsonl
```

The full JSONL is 41 MB and remains on the server because it contains source
dataset text. Only the lightweight summary is committed.

## Pool Composition

The generated pool contains 1300 unified samples:

```text
RULER synthetic niah_single_1: 200
LongBench hotpotqa: 200
LongBench qasper: 200
LongBench narrativeqa: 200
RepoBench python_v1.1: 500
```

Partitioning is deterministic:

```text
partition = sha256(seed|dataset|task|sample_id)[0] % 10
seed = 14014
0-1: calibration
2-3: held_out_quality
4-9: live_serving
```

Observed partition totals:

```text
calibration: 283
held_out_quality: 254
live_serving: 763
```

## Dataset Sources

LongBench is read from the local cached JSONL files under:

```text
datasets/downloads/extracted/*/data/{hotpotqa,qasper,narrativeqa}.jsonl
```

RepoBench is read from the local cached parquet file under:

```text
hub/datasets--tianyang--repobench_python_v1.1/snapshots/*/data/in_file*.parquet
```

RULER is generated through the existing deterministic ContractKV sample builder.

No HuggingFace network access is required for this step.

## Artifact Integrity

```text
phase14d_full_pool_v0.jsonl
sha256: cbfb9592b74ac0d577fe71de3c1b8ee197bbe985b0d79fc5cfde976a179f9b97

phase14d_full_pool_summary_v0.csv
sha256: 5fff675f73adb61636231c1acb362c566e0db30d38badb8144cf994ea4093f94
```

Disk check after generation:

```text
/dev/sdb5       219G  181G   27G  88% /
/dev/sda1       7.3T  239G  6.7T   4% /media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9
```

## Claim Boundary

This artifact proves that Phase 14D no longer depends on the 140-sample quick
verification pool. It provides a larger and disjoint workload basis for:

```text
Phase 14C full-pool QC calibration
Phase 14D large-scale mixed live serving
Phase 14E ablations and oracle-gap analysis
```

It does not yet prove the final paper performance gates. Those require fresh
live vLLM endpoint runs and held-out task-quality scoring on the partitions
defined here.
