# Reproduce the query-bound repair supplement

This supplement preserves the original submitted study and the completed R1
stress matrix. It tests a repair on a new source-disjoint cohort. The original
negative results are in `tsc_major_revision_r1_results.md`; they are not erased
by later successful measurements.

## Frozen scope and interpretation

The prospective protocol is
`configs/tsc_revision_r1r_validation_protocol_v1.json`. Its 45 cells contain
28,350 actual future generations, with three models and three fresh process
repeats. Raw-order and all fallback routes remain in the measured population.
The 50 sealed source templates were selected before development was measured;
the ten-template fan-out subset takes the first two committed sources per
family. The single-session and fan-out studies share some sources and are
reported separately. These are closed-loop replays at concurrency two. The
fan-out study registers 100 tenant sessions over ten templates; it does not
claim 100 simultaneous active requests or open-loop load capacity. The original
R1 zero-slack service experiment supplies separate open-loop evidence.

Query text, system message, stable content, model, generation budget and
renderer identity are bound. A new query is served raw first. Its actual raw
business output supplies the witness; no duplicate raw answer is generated for
registration. The only suffix changes admitted here are the declared
metadata-only tool-observation schema. This is an empirical scope boundary,
not a semantic guarantee for arbitrary future tool content.

The conservative repair is a query-catalog mode: attestation work grows with
the number of distinct exact query scopes. The fan-out trace deliberately
reuses the same benchmark questions across tenants, rather than measuring the
prevalence of repeated queries in production. It does not establish an O(1)
certificate for arbitrarily many unseen queries or a speedup on a unique-query
stream. Keep it separate from the submitted service-template qualification
results and their originally authorized trajectories.

The inherited per-model family maxima are documented in the live runner.
Uniform level descent never exceeds those maxima. Mistral/Llama Qasper and
RepoBench raw routes remain in the totals. No held-out quality threshold,
family maximum or routing rule is tuned after observing validation outcomes.

These are controlled repair-study variants, not a reproduction of the complete
published adaptive policy. They keep rank-one answer/EOS checks and uniform
allowed-level descent. The launchers set candidate-margin and degradation
bounds to -1e9/+1e9, so those auxiliary robustness guards do not select routes;
the original frozen profitability gate is not executed here. `query-full`
means full-context witness computation, not every guard in the original policy.
This scope is the same for both query-bound verification variants and prevents
their measurements from silently replacing the submitted all-workflow table.

## Runtime

Use the R1 Linux environment: torch 2.8.0+cu128, vLLM 0.10.2,
transformers 4.55.2, triton 3.4.0, numpy 2.2.6, FP16, two RTX 3090 24 GB
GPUs and concurrency two. Each cell records package versions, model
configuration/tokenizer/index identities, shard presence and physical GPU state.
Model weights are not redistributed.

Start from the R1 serving source described in `tsc_revision_r1_reproduce.md`.
Apply `third_party/patches/contractkv_r1r_prefix_witness_v1.patch` once; the
six-file final source identities are in
`configs/tsc_revision_r1r_backend_commitment_v2.json`. The earlier
`contractkv_r1r_prefix_read_only_v1.patch` is a development intermediate and
must not also be applied. No attention kernel or model weight is modified.

The final patch allows internal witness requests to borrow only an approved,
matching stable prefix. Unapproved chains, foreign namespaces and wrong policy
identities receive no read. It extracts only answer/EOS logprob rows; the
necessary Transformer/KV computation remains intact. A rejected attempt inserts
no new candidate hashes. Generic prompt-logprob behavior remains unchanged.

`CONTRACTKV_SHADOW_CHUNK_TOKENS=128` and
`CONTRACTKV_SHADOW_ROUND_TOKENS=128` are the actual scheduler settings.
The unused development variable ending in QUANTUM did not change scheduling and
is not credited as a measurement of the 128-token setting.

## Execution and exact evidence

The input commitment is under `results/tsc_revision_r1r/inputs/`.
`validation/freeze_v1.json` records source/input SHA256 values before validation.
Its source snapshot preserves the exact client and six runtime source files.
The per-cell manifest checks those source hashes again before starting a server.

On a prepared matching Linux deployment, use:

```bash
python scripts/tsc_revision_r1r_freeze_validation.py --root .
bash scripts/run_tsc_revision_r1r_validation.sh
python scripts/tsc_revision_r1r_validation_summary.py \
  --root results/tsc_revision_r1r/validation \
  --output results/tsc_revision_r1r/validation/summary
```

The freeze refuses replacement and cells refuse overwriting raw files. Reusing
an existing package requires verifying its freeze and running only genuinely
missing cells in a separately logged continuation; never start another copy
after an SSH observation timeout. The immutable launcher snapshots and original
PID state identify the running batch.

Each cell also runs seven separate cold/read/namespace/rejection controls before
the measured business interval. Those requests use separate cache namespaces and
do not count as future business requests. Warm business requests do count toward
full wall time. Full wall includes first-use raw generations, tokenization,
all failed verification attempts and actual controller waits. No tool slack is
subtracted. Server startup and preliminary controls are excluded equally from
all policies. Readiness TTFT begins at the preceding business-wave completion;
backend request TTFT is retained separately.

The summed complete-verification milliseconds aggregate registration calls,
including failures. Parallel calls can overlap. This diagnostic sum must not be
added again to the already observed readiness TTFT or full wall time.

Specifically, the two sessions in a cohort advance through a shared turn
barrier: the next wave is ready after both preceding outputs finish. The
recorded readiness interval includes preparation, verification and dispatch
after that barrier. Independent per-tenant readiness at each earlier individual
completion is not measured. Full wall time still charges every within-wave
wait, so the closed-loop throughput denominator does not discard that time.

Quality pairs retain actual returned token IDs, first token divergence, task
score differences and length stops. Source templates are the resampling unit;
tenants and future turns remain correlated within source. Readiness intervals
resample paired repeats and source templates. Full-wall goodput reports three
fresh-repeat paired values and min/max, rather than inventing an additive
source-level wall-clock interval.

The repair trace does not separately archive per-request prompt token IDs or
their hashes. Input-repeat identity relies on the committed sample/session/turn,
deterministic renderer and model/configuration manifests, with actual server
prompt counts retained. Do not describe this as a direct per-request prompt-ID
hash match. A later numerical replay should add that logging without rewriting
the current frozen study.

GPU lanes follow the frozen task-index modulo-two assignment. Some raw/policy
pairs use different physical cards of the same RTX 3090 type. The per-cell
hardware snapshots and `launcher_gpu_assignment_v1.csv` record this context.
`within_gpu_lane_diagnostic_v1.csv` separately compares run means on each lane
where both policies have data; its small, unequal run counts are explicit. This
is a post hoc hardware diagnostic, not an additional randomized experiment or
a replacement of the primary paired-repeat estimands.

The inherited verifier checks rank-one membership reported by vLLM for every
raw answer token and the terminal stop. Equal maximum scores can share rank
one; this interface does not establish a unique greedy winner under ties.
Together with finite-precision differences between teacher forcing and decode,
this is another reason to retain actual free-running outputs as the behavioral
evidence. No bitwise or universal future-input theorem is claimed.

## Long-output supplement

`configs/tsc_revision_r1r_long_horizon_protocol_v1.json` freezes a separate
controlled array-generation task. It measures 256/512 caps and a 1536 cap that
allows naturally terminated outputs longer than 512. A larger cap alone is not
positive long-output evidence: report actual generated lengths and EOS status.
Length-stop references must abort before promotion. This supplement contains
nine fresh cells, 27 raw reference generations and 108 raw/policy future
generations. It supplies behavioral mechanics evidence, not official benchmark
task quality or service performance. Its templates are not pooled into the
five-family quality table.

The deployment launcher queues this supplement behind the completed validation
marker so it cannot contend with the formal performance matrix. The queue's
recorded parent PID is specific to the original execution and must be updated
deliberately for a fresh deployment.

## Known-counterexample followup

All four model/source units with native-budget admitted regressions in R1 are
selected for a separate diagnostic. Their original inputs and IDs are retained.
One fresh server per model runs raw order, the legacy unbound-scope client, then
the query-bound prefix-assisted client: nine policy cells, 108 future
generations. Policies share that model's server and use the same new backend.
The legacy client is a controlled scope-logic adaptation, not a reproduction of
the original runtime or batch shapes; no timing advantage is claimed here.

Selection deliberately uses known failures. These cases cannot enter the new
held-out success rate. Report whether the legacy logic actually reproduces a
regression under this control and what the new route does; a non-reproduction
must not be called a repaired failure. The prospective inputs/source hashes are
in `known_counterexamples/freeze_v1.json`. The followup waits until the primary
and long-output raw archive is finalized and is published as separate evidence.

The frozen `tsc_revision_r1r_known_summary.py` remains unchanged. An additional
post-execution `tsc_revision_r1r_known_summary_audit_v2.py` checks the exact
committed source/session/turn/model/policy set, actual metric events and token
usage before the separate archive is built. Its outputs are under
`known_counterexamples/additional_audit_v2/`; they do not overwrite the frozen
original analysis. The long-output auditor also checks the exact cap/turn and
model/repeat coordinates and recalculates array scores from response text.
These are strengthened evidence checks, not new admission or scoring rules.

`tsc_revision_r1r_freeze_audit.py` compares every committed source/input with
both its immutable snapshot and the current deployment bytes. Point-in-time
checks before the remaining experiments and at final closure are retained;
they do not establish uninterrupted historical filesystem identity. A temporary
mistaken edit to the frozen known-case analysis was restored before that queued
study started. Its restoration hash and queue state are recorded in
`results/tsc_revision_r1r/analysis_change_record_v1.json`; generation sources,
inputs and backend files were not changed by that edit.

## Claims left outside scope

Correctly signed manifests can still mislabel private content. The verifier
checks behavior and identity, not confidentiality. Shared-prefix timing
channels, adversarial tool semantics, distributional equivalence, stochastic
decoding and production workload prevalence are not established here.

The live harness acts as a trusted operator and connects to the localhost-only
prototype endpoint. The nine-case manifest registration validator is a separate
CPU component audit; that helper is not invoked by the live vLLM endpoint. Do
not describe its issuer/role checks as an end-to-end adversarial tenant test or
a deployed confidentiality defense. The live cache-namespace/policy and
transaction-publication controls are separate evidence.
