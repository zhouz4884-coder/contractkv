# Phase 2.7 Dataset Readiness Report

This report is generated from `results/datasets/dataset_readiness.csv`, `results/datasets/sample_prompts.jsonl`, and `results/datasets/segment_examples.jsonl`.

Phase 2.7 validates dataset access and segment extraction only. It does not claim official benchmark scores.

## Result

The three local source zip files were uploaded to the 8T disk and extracted. The server could not download LongBench/RepoBench directly from HuggingFace, so LongBench and RepoBench were prepared locally and uploaded as `contractkv_datasets.zip`.

The offline bundle was extracted on the 8T disk at:

`/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/datasets/contractkv_datasets`

Dataset readiness status:

| Dataset | Status | Samples | Note |
| --- | --- | ---: | --- |
| RULER | ready | 20 | Synthetic NIAH-style samples generated from the local source repo. |
| LongBench | ready | 100 | Loaded locally via HuggingFace `THUDM/LongBench`, uploaded through `contractkv_datasets.zip`, and normalized into the unified segment schema. |
| RepoBench | ready | 20 | Loaded locally via HuggingFace `tianyang/repobench_python_v1.1`, uploaded through `contractkv_datasets.zip`, and normalized into the unified segment schema. |
| BFCL | missing_optional | 0 | Not part of `characterization_batch_001`. |

`sample_prompts.jsonl` now contains 140 samples:

- RULER: 20
- LongBench: 100
- RepoBench: 20

RepoBench remains `evaluation_ready=false` at the sample metadata level because Phase 2.7 validates data readiness and segment extraction only, not official RepoBench scoring.

## Network Note

Direct server-side HuggingFace downloads remain unavailable in this environment: previous attempts to reach `THUDM/LongBench` and `tianyang/repobench_python_v1.1` failed with connection reset / `LocalEntryNotFoundError`. The reproducible route for this batch is therefore:

1. Download or materialize HF datasets locally.
2. Package the lightweight prepared outputs and HF cache as `contractkv_datasets.zip`.
3. Upload the zip to the 8T disk.
4. Merge only lightweight CSV/JSONL artifacts into the Git repository.
