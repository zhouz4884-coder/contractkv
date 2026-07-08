# Phase 2.7 Dataset Readiness Report

This report is generated from `results/datasets/dataset_readiness.csv`, `results/datasets/sample_prompts.jsonl`, and `results/datasets/segment_examples.jsonl`.

Phase 2.7 validates dataset access and segment extraction only. It does not claim official benchmark scores.

## Result

The three local source zip files were uploaded to the 8T disk and extracted. Dataset readiness status:

| Dataset | Status | Samples | Note |
| --- | --- | ---: | --- |
| RULER | ready | 20 | Synthetic NIAH-style samples generated from the local source repo. |
| LongBench | download_unavailable | 0 | Source repo exists, but HuggingFace access to `THUDM/LongBench` failed with connection reset / `LocalEntryNotFoundError`. |
| RepoBench | download_unavailable | 0 | Source repo exists, but HuggingFace access to `tianyang/repobench_python_v1.1` failed with connection reset / `LocalEntryNotFoundError`. |
| BFCL | missing_optional | 0 | Not part of `characterization_batch_001`. |

`sample_prompts.jsonl` currently contains 20 RULER samples with segment token counts. LongBench and RepoBench are not marked ready and are not used for official scoring.
