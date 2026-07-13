# Phase 19A: Frozen-Provenance Quality Rebuild

## Scope

Phase 19A rebuilds the complete 734-candidate quality pool under one frozen
Qwen3-8B provenance. It preserves the existing 357-row calibration and 377-row
held-out split, does not retune the Phase 17R policy, and treats verifier margins
as telemetry only.

This phase closes the quality-evidence provenance gap. It does not measure
future-turn cache reuse or end-to-end serving goodput; those remain Phase 19B.

## Frozen Runtime

- Model revision: `f7c4eadf...447c30`
- Tokenizer hash: `1439faf0...fb7e2`
- Chat-template hash: `41d5929b...c947d`
- vLLM: 0.10.2 source revision `0a336eeb2a62198b8f6d27a079657df5e126a5c6`, clean tree
- Policy hash: `55e10dc4f54daf428b382a35fe8a8feeded5b4b3f34752f36f45c8f825df1ee4`
- Decode: greedy, seed 0, maximum 96 tokens, token IDs and top-2 logprobs
- Terminal protocol: exactly one returned terminal stop token

The server ran from the 8 TB project tree with Qwen3-8B on one RTX 3090. Its
capacity was 16K, while candidate construction remained frozen at 8K so that
all v5 candidate identities and prompt truncation decisions stayed unchanged.

## Method

The 1,273-job manifest contains 539 shared raw layouts and 734 candidate
layouts. Each raw layout received a fresh free decode. Each candidate received
a fresh free decode and, when the raw terminal protocol was complete, an
intrinsic teacher-forced attestation of the raw answer token path under the
candidate prompt.

`finish_reason=length`, missing terminal metadata, and unavailable competitor
logprobs are `INCOMPLETE` and fail closed. Candidate identity is reconstructed
from the frozen builder independently of generation success. This distinction
fixed one audit-only implementation defect where a margin-extraction failure
was initially mislabeled as an identity mismatch; the model outputs were not
changed or rerun.

## Audit Gates

| Gate | Result |
| --- | ---: |
| Candidate rows | 734 / 734 |
| Unique candidate identities | 734 / 734 |
| Identity auditable | 734 / 734 |
| Complete provenance | 734 / 734 |
| Candidate identity mismatch | 0 |
| Duplicate / missing / extra rows | 0 / 0 / 0 |
| Stale legacy label reused | 0 |
| Unexplained join mismatch | 0 |
| Unknown protocol error | 0 |

Four labels differ from the historical pool. They are reported as provenance
drift telemetry; all policy statistics below use only the fresh labels.

## Frozen Results

| Split | Candidates | Complete | Incomplete | Safe | Unsafe | Certified | Safe coverage | Unsafe certified | Retained expected prefix gain |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Calibration | 357 | 342 | 15 | 325 | 17 | 243 | 74.77% | 0 | 70.75% |
| Held-out | 377 | 350 | 27 | 339 | 11 | 244 | 71.98% | 0 | 69.14% |
| All | 734 | 692 | 42 | 664 | 28 | 487 | 73.34% | 0 | 69.91% |

All 28 fresh unsafe candidates were rejected, including all 11 held-out unsafe
candidates. The 487 certificates retain 1,793,809 of 2,565,843 expected safe
prefix-gain tokens. These are compiler estimates, not observed vLLM cached-token
hits. The 42 fail-closed incomplete rows account for 219,299 expected-gain
tokens of opportunity loss; 40 of those rows are RepoBench, one is Qasper, and
one is NarrativeQA.

Verifier decisions were 488 PASS, 219 FAIL, and 27 INCOMPLETE. Certificate
eligibility is one lower than PASS because quality safety is an independent
gate: a verifier PASS cannot override a fresh unsafe task-quality label.

## Interpretation

The main quality-control result is strong and properly bounded: under one
frozen model/tokenizer/template/builder/evaluator/policy lineage, ContractKV
rejects every freshly observed unsafe candidate while certifying 73.34% of
complete safe candidates. The held-out result is 71.98% safe coverage with zero
unsafe certification.

The task scores are the repository's task-sanity evaluator, not official
RULER/LongBench/RepoBench benchmark scoring. Expected prefix gain is also not a
serving result. Phase 19B must connect these certificates to physical future-turn
reuse, net TTFT reduction, and SLO goodput on an untouched task-bearing split.

## Actual Code Used

The following non-test files directly participated in producing or freezing
this result:

- `scripts/phase19a_rebuild_quality_pool.py`
- `scripts/phase19a_audit_provenance.py`
- `scripts/phase19a_freeze_quality_summary.py`
- `scripts/run_phase19a.sh`
- `scripts/contractkv_frozen_policy.py`
- `scripts/contractkv_verifier.py`
- `scripts/phase14c_full_pool_qc_inputs.py`
- `scripts/phase14c_run_full_pool_quality_jobs.py`
- `scripts/phase13b_fresh_policy_quality_replay.py`
- `scripts/phase12f_real_vllm_caposc_replay.py`
- `scripts/phase12_task_quality_sanity.py`
- `scripts/phase16r_verifier_live.py`
- `scripts/phase17_live_common.py`

## Evidence

- `results/quality/phase19a_frozen_provenance_manifest_v0.json`
- `results/quality/phase19a_frozen_quality_v0.csv`
- `results/quality/phase19a_provenance_audit_v0.csv`
- `results/quality/phase19a_provenance_audit_summary_v0.json`
- `results/quality/phase19a_frozen_quality_summary_v0.csv`
- `results/quality/phase19a_frozen_quality_summary_v0.json`

The resumable raw generation caches remain on the 8 TB server volume. Their
SHA-256 values are recorded in the Phase 19A manifest.
