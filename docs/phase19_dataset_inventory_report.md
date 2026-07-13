# Phase 19 Dataset Inventory

## Result

The 8 TB server volume contains all four source archives used by ContractKV,
all three extracted repositories, and the locally generated unified prompt
pool. The machine-checkable inventory gate passes.

The Phase 14D unified pool has 1,300 rows:

| Dataset | Rows |
| --- | ---: |
| LongBench | 600 |
| RULER | 200 |
| RepoBench | 500 |

Its frozen partitions contain 258 calibration rows, 281 held-out-quality rows,
and 761 live-serving rows. The live-serving partition includes 118 HotpotQA,
118 NarrativeQA, 113 Qasper, 107 RULER, and 305 RepoBench examples. RepoBench
contains 275 unique source groups in the live-serving partition; every other
task row in that partition has a distinct source group.

## Assets

The following assets are present under
`/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/datasets`:

- `sources/RULER-main.zip`
- `sources/LongBench-main.zip`
- `sources/repobench-main.zip`
- `sources/contractkv_datasets.zip`
- `repos/RULER-main/`
- `repos/LongBench-main/`
- `repos/repobench-main/`
- `contractkv_datasets/outputs/sample_prompts.jsonl`

The source archives occupy about 924 MB, extracted repositories about 11 MB,
and the local ContractKV dataset bundle about 2.4 GB. These paths are on the
large data volume, not the system disk.

## Interpretation

The server is not limited to a few sessions. Phase 19B deliberately uses a
balanced 50-session untouched split for controlled live serving, and its
multi-turn policy/load matrix produces thousands of measured requests. The
1,300-row pool remains available for a later full official quality-scoring
run. Asset presence and unified-pool readiness do not by themselves mean that
official RULER, LongBench, and RepoBench scoring has already run on every
source example.

## Evidence

- `results/datasets/phase19_dataset_inventory_v0.csv`
- `results/datasets/phase19_dataset_inventory_summary_v0.json`
- `scripts/phase19_dataset_inventory.py`
