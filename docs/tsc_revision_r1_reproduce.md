# Reproducing the R1 Experimental Evidence

## Boundaries

This package is the major-revision experimental supplement for
TSC-2026-07-1067, not a replacement of the submitted manuscript or its frozen
historical tables. Main session replay, zero-slack service replay, historical
reanalysis, and CPU registration checks have distinct measurement boundaries.
Read `tsc_revision_r1_measurement_definitions.md` before comparing their numbers.

All original R1 held-out results, including task-score regressions, are retained.
No family level, quality threshold, query wrapper, or output budget was changed
after the formal matrix was observed. Experiment completion is not a declaration
that all desired scientific gates passed.

## Frozen Inputs and Runtime

- `configs/tsc_major_revision_r1_protocol.json`: frozen primary protocol.
- `configs/tsc_revision_hotpot_development_sessions_v1.jsonl`: five compatibility
  inputs, not part of the common held-out denominator.
- `configs/tsc_revision_hotpot_heldout_sessions_v1.jsonl`: 30 identical HotpotQA
  source sessions for all three models, fixed L2 and 10 turns.
- `configs/tsc_revision_free_generation_sessions_v1.jsonl`: 50 source-disjoint
  sessions, ten per family, original budgets plus a separate 512-budget condition.
- `configs/tsc_revision_qwen14_cost_protocol_v1.json`: supplementary 25-session
  FP16/TP2 cost measurement on the already evaluated Qwen3-14B model.
- `results/tsc_revision_r1/input_commitment_v1.json`: source-pool, exclusion and
  input identities. No source group is selected by measured outcome.

The actual runtime is Linux, two RTX 3090 24GB GPUs, torch 2.8.0+cu128,
vLLM 0.10.2, transformers 4.55.2, triton 3.4.0, numpy 2.2.6 and driver
570.133.07. Model config/tokenizer identities and shard presence are recorded
per cell. Weight files are not redistributed in this repository.

`runtime_source_inventory_v1.json` records the official v0.10.2 tag, the
compact-channel source base, the final source patch and linked extension hashes.
`vllm_0102_revision_runtime_v1.patch` includes all five changed Python source
files relative to the official tag, including the installed shadow and prefix
metric hooks. Do not apply the hook installers a second time after this patch.
The CUDA extension ABI must match the installed vLLM 0.10.2/torch 2.8.0 stack.

The exact client used by the 54-cell main matrix is
`results/tsc_revision_r1/source_snapshots/tsc_revision_live_main_v1.py`, SHA256
`fa3b7302bb2ed00807cd3af0885198188f6ec4c77ccd5f5bf04123de66505954`.
The current `scripts/tsc_revision_live.py` adds only Turn-0 reference/warm output
logging. Its result algorithm and stable-only publication boundary are unchanged.
Earlier canary output IDs are unavailable; later future IDs are actual returned
vLLM IDs, never text retokenizations.

The supplementary TP2 wrapper also runs a separate post-decision guard probe
after its first available completed ContractKV cell. That probe's timing and
twenty actual business outputs are not appended to the finalized main cell.
The pre-guard wrapper and original 8B guard sources are retained as separate
source snapshots. The original 8B probe's effective score was routing-accounted;
the added TP2 probe records fresh post-decision token IDs and outputs.

## Linux Execution

The shell entrypoints accept `ROOT`, `CONTRACTKV_DISK_ROOT` and `PYTHON_BIN` for
the primary/followup batches. The supplementary TP2 launcher records the actual
deployment paths used in this run. Point models to the frozen local weight
directories, keep caches and results on the data disk, and pin the source path
through `PYTHONPATH`. Each cell starts and stops its own server.

```bash
bash scripts/run_tsc_revision_r1_batch.sh
bash scripts/run_tsc_revision_r1_followup.sh
bash scripts/run_tsc_revision_qwen14_cost.sh
```

The first two commands use the following input names under the run root:
`results/tsc_revision_r1/inputs/hotpot_heldout_sessions_v1.jsonl`,
`free_generation_sessions_v1.jsonl`, `service_sessions_v1.jsonl` and per-model
service protocols. The raw-evidence archive retains the exact service and 14B
inputs. Primary inputs are also versioned in `configs/`.

Main cells refuse to overwrite existing raw files. Whole-cell summaries are
checkpoints, not permission to resume a partial stream. Any failed attempt must
be inspected and moved to a named quarantine before a fresh complete attempt.
Orchestration uses immutable shell snapshots to avoid editing an executing bash
file. Never start a second copy because an SSH observation timed out.

The main cells use greedy generation, temperature 0, top_p 1 and seed 14014.
Actual service streaming requests retain the original frozen service harness.
Policy hash and generation/runtime/manifest bindings are recorded. A changed
output budget requires a new attestation. The API is operator-internal and bound
to localhost; the random in-memory signing secret is not a public artifact.

## Analysis and Audit

Verify the archive SHA256 against `raw_evidence_archive_manifest_v1.json` and
extract from the repository root:

```bash
tar -xzf results/tsc_revision_r1/r1_live_raw_evidence_v1.tar.gz
```

Members contain the actual cell files, metric observations, server logs and
frozen input files under their original repository-relative paths. The
`raw_evidence_inventory_v1.csv` hashes every archived file individually. The
archive excludes passwords, SSH helpers, quarantine, weights and caches.

The full archive exceeds GitHub's per-file limit and is transported as 32-MiB
binary parts, not recompressed subsets. Verify each part against
`raw_evidence_parts_manifest_v1.json`, concatenate in numeric order, and verify
the reassembled archive hash before extraction:

```bash
cat results/tsc_revision_r1/r1_live_raw_evidence_v1.tar.gz.part* \
  > results/tsc_revision_r1/r1_live_raw_evidence_v1.tar.gz
```

```bash
python scripts/tsc_revision_summarize.py \
  --root results/tsc_revision_r1 --output results/tsc_revision_r1 \
  --bootstrap-samples 10000
python scripts/tsc_revision_diagnostics.py \
  --root results/tsc_revision_r1 --output results/tsc_revision_r1
python scripts/tsc_revision_service_summary.py \
  --root results/tsc_revision_r1 --logs logs/tsc_revision_r1 \
  --output results/tsc_revision_r1
python scripts/audit_tsc_revision_r1_completion.py \
  --root results/tsc_revision_r1 \
  --output results/tsc_revision_r1/remote_completion_audit_v1.json
python scripts/tsc_revision_report.py \
  --root results/tsc_revision_r1 \
  --output docs/tsc_major_revision_r1_results.md
```

The completion audit must be run on extracted actual raw cells, not a directory
holding only compact summaries. A missing local mirror is not evidence that the
remote job failed. The public archive contains raw outputs, summaries, input and
source manifests; its SHA256 inventory is retained separately. Metrics and
server logs remain separate evidence from teacher-forced certificate reports.

`actual_result_code_inventory_v1.csv` lists the non-test entrypoints and helpers
that contributed to results. It separates research analysis, CPU security checks
and actual serving-engine files. SSH/password tools are deliberately excluded.

## Security and Scientific Limits

Raw-reference path agreement is prompt- and generation-bound. A stable-prefix
hash does not prove agreement for a new query wrapper, and zero recorded
field-level scope violations does not imply universal behavioral validity.
The new stress-test regressions must remain visible in the revised argument.

Registration hashing/signing does not infer confidentiality. A trusted operator
can mislabel private text as public; this is explicitly demonstrated, not hidden.
Authorization-domain isolation does not prevent shared-prefix timing inference.
The prototype has no timing-channel defense and no distributed-cache transaction
implementation in this experimental package.

No password, decrypted credential, private credential helper, or raw SSH-origin
resource-transition record is included in the public package. The password
rotation archive is stored outside the repository under Windows current-user
DPAPI protection.
