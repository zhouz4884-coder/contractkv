# TSC Major Revision R1: Experimental Closure

Decision letter: TSC-2026-07-1067, received before this revision batch.
Revision deadline: 2026-12-13. The objective is to close the requested evidence
gaps, with the original frozen submission retained as an immutable baseline.

## Requirements and evidence

| ID | Reviewer request | Required evidence | Status |
|---|---|---|---|
| X1 | R1 non-RULER common scope | Three models, 30 identical HotpotQA sessions, 10 turns, three fresh raw/ContractKV pairs; all fallbacks included | completed: 9 pairs; 2430 paired futures |
| X2 | R1 free-running behavior and output horizon | Independent task contexts; raw-reference attestation; actual free token IDs, first divergence, scores, completion and length stops at original budgets and 512 | completed: 18 pairs; 8100 paired futures; future-scope safety failures retained |
| X3 | R3 full verification cost | Four-model historical full-cost reanalysis, admitted/fallback decomposition; fresh zero-slack D0/D1/D2 on Qwen/Mistral | completed: live zero-slack service and Qwen14 TP2 supplement; missing historical clocks remain unavailable |
| X4 | R3 certification beyond safe reordering | Identical safe/unsafe candidate sets; D1 vs D2 output quality, rejection and zero-publication events | completed: both 20-case guards, including fresh post-decision outputs; 10/10 bad layouts rejected, zero rejected publication |
| X5 | R1 manifest trust and tenant isolation | Registration ownership/binding cases; detection limits for operator mislabelling; bounded timing diagnostic or explicit limitation | completed: nine CPU cases and explicit timing-channel limitation |
| X6 | R1 CacheBlend fairness and CI; R2 input differences | Matched-baseline regression thresholds, runtime/configuration inventory, paired-session macro CI audit, token positional displacement | completed: 9000 native-matched pairs, joint-source bootstrap, 4695 segments |
| X7 | Reproducibility and closure | Protocol/source hashes, environment snapshot, result-producing file list, CSV/JSON/Markdown and verified GitHub upload | pending |

The protocol is `configs/tsc_major_revision_r1_protocol.json`. Its hash and all
input commitments must be saved before any new held-out measurement. A failed
cell is retained, and any rerun is a fresh complete process with a distinct
attempt ID. No success subset replaces the global result.

## Execution

1. Pin SSH identities; inspect current model integrity, environment, data disk,
   raw archives, and GPU ownership. Do not interrupt unrelated active jobs.
2. Create a separate revision source copy and cache namespace on the 8 TB disk.
   Preserve archived scripts and historical results without overwriting them.
3. Produce X3/X6 offline audits while preparing X1/X2 inputs. Freeze source-group
   selection, common L2 ordering, budgets, scope, and thresholds.
4. Smoke-test raw-reference attestation, intentional FAIL, length-stop abort,
   prompt identity, block metrics, and generation binding before main cells.
5. Run X1 and X2 with fresh processes, then X3/X4 live service probes and X5.
   Keep raw/fallback denominators and measured verification wall time.
6. Summarize paired results with repeat/session clusters; verify every required
   artifact and publish only the revision's code and compact evidence.

## Audit findings before new measurements

- The legacy service-template quality runner obtains its reference output from
  `candidate_messages`. This establishes candidate self-consistency under its
  prospective template qualification; it is not raw-path attestation. New R1
  measurements must use raw prompt output and retain this provenance distinction.
- The historical zero-slack Qwen table is offline accounting over measured
  canary latency and live TTFT. It cannot be relabelled as fresh live goodput.
- The original common-scope macro bootstrap samples sessions independently
  within each model. R1 must explain the fixed-model estimand and also resample
  identical source sessions jointly across models.
- Initial 3090 GPUs were occupied by an unrelated live RADAR experiment. V100
  GPU2 is available, but the existing vLLM source/toolchain compatibility gate
  remains to be revalidated. These are resource/runtime findings, not outcome
  evidence for ContractKV.

The user subsequently authorized stopping the two RADAR GPU workers and their
coordinators. Their SSH-origin launch was audited and their files preserved.
No other project was stopped. The 3090 password was changed at the user's
request and stored outside the repository with Windows current-user DPAPI;
no plaintext password is part of the research package.

## Reporting boundary

Certification tests greedy token paths for a bound generation configuration.
Across later prompts, it is an empirical scoped admission mechanism. The
free-running experiment measures whether admitted later prompts diverge and
how divergence affects task score. Hashing and HMAC do not infer confidentiality
or correct an operator's semantically wrong manifest declaration. Authorization
does not imply elimination of shared-prefix timing channels.

The existing 325,000 operations are CPU state-machine stress, not GPU requests.
New evidence must preserve that distinction. Manuscript and response-letter
revisions follow completion of the experimental audit; the original submission
PDF is not overwritten by this batch.
