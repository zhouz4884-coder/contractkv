# Phase two: measured repair of residual revision failures

The phase-one report was delivered before this work began. Its public closure
commit is `3dba4e58f406cc427f83f23379abe3d3567cf301`. Original R1/R1R data,
thresholds, snapshots and reported failures remain immutable. This stage is
authorized optimization, not a reinterpretation of those outcomes.

## Gate 1: distinguish mechanisms before choosing a repair

The two compiled failures from the new matrix become selected development
cases. Llama's three raw controls have identical scores and token IDs; Mistral's
raw output varies. Neither observation proves an implementation or numeric
cause. In Llama's failed qualification the approved-prefix read count was zero.

`configs/tsc_revision_r2_diagnose_v1.json` freezes two known cases, their original
witness/future tenant and turn, every candidate level, three sequential repeats,
and counterbalanced level order. One fresh server per model runs singleton
requests on a fixed GPU with the unchanged phase-one backend and wide auxiliary
bounds. Internal approved-prefix reads are disabled. Unique salts isolate each
request; actual prefix counters are retained rather than assuming a cache hit.

Every nonstream free generation retains the server-returned complete prompt IDs
and checks them against `/tokenize`; the generic full-logprob request directly
uses the forced IDs and checks the server echo. Each same-prompt control compares
raw/candidate free output, complete answer/EOS logprob rows, and the internal
answer/EOS extraction path using the same fresh business witness. JSON responses,
individual token ranks/margins, text, official scores and actual metrics remain
available. Expected counts are 48 free generations, 42 full-logprob requests and
30 internal requests. Full-logprob calls also decode one continuation token;
they are diagnostic operations, not business throughput samples.

These are three repeats within each server, not three independent process
replications. The singleton/cold condition is not a reproduction of the prior
concurrent warm scheduling trace. If a failure does not recur, retain that result
and add separately frozen batch/cache/metadata controls before attributing it.
Prospective files are snapshotted before launch and the old 83 commitments are
rechecked. Native extensions, model metadata/shards and available GPU resources
are checked again. No backend or generation policy is changed in this first
diagnostic.

The first cold diagnostic did not reproduce the material drops; its actual
responses and all 120 engine observations are preserved. A separate
`tsc_revision_r2_warm_reuse_v1.json` condition fixes L2 and the same known cases.
It first qualifies into a dedicated diagnostic salt, then compares unique-salt
cold generation with same-salt generation that can consume the newly committed
KV. Both witness and future metadata prompts are checked, and cold/warm order
rotates across three sequential repeats. Two fresh servers execute 42 free
generations and six internal qualifications. Actual prefix hits, rather than
the salt name, determine whether a reuse condition was exercised. No behavioral
guard or backend changes are included. This separates post-qualification cache
execution from the cold-only condition before adding a batch-shape experiment.

The matching-salt singleton control also did not reproduce the original drops:
all 12 same-prompt cold/reuse pairs exercised actual qualified hits without token
differences. The next frozen `tsc_revision_r2_batch_reuse_v1.json` adapter keeps
that driver unchanged and pairs each chat call with the next tenant's metadata
request. It retains both complete responses. Cold twins use distinct salts;
qualified twins share the already attested salt. Across two servers this adds
42 twin generations to 42 primary generations and six qualifications, totaling
90 actual requests. HTTP overlap and a scheduler observation with two active
requests are required; these do not supply per-step kernel batch telemetry.
This is a controlled concurrency adaptation, not an exact reproduction of the
original long service trace. Three repeats remain within each fresh process.

## Gate 2: development repair and separate validation

After the controls, choose a repair supported by observed target-task evidence.
Candidate explanations include metadata scope sensitivity, teacher-forced versus
decode arithmetic, ambiguous ranks/margins, or an implementation difference.
They remain hypotheses until the controls separate them. A guard chosen from a
known failure cannot be validated on that same failure alone.

Freeze a new source-disjoint validation cohort before opening its outcomes.
Retain first-use raw, every rejected attempt, fallback, actual prompt/output IDs,
task scores and source-cluster statistics. Report any compiled material drop
above 0.03 and all raw-control variation. Zero scope-invalid admission and zero
rejected publication remain hard invariants; empirical zero quality drops would
be a bounded observation rather than a theorem.

## Gate 3: service cost and long-output behavior

Use the measured development cost decomposition to improve cold-session
admission: first witness, repeated failed levels and controller waits are charged
to actual wall. Reuse must pay for qualification within the tested workload.
Evaluate readiness mean/p99 and full-wall throughput against raw and the frozen
phase-one repair, with quality constraints retained. A reduction in summed
verifier time is insufficient by itself.

Run clearer long-output format instructions as a separately frozen condition.
The original Llama marker and Mistral string-array failures keep their original
scores. Count actual returned lengths, stop/EOS, syntax/type/value predicates and
raw-versus-policy divergence. Do not pool this mechanics task with benchmark
quality or call a fallback a positive compiled long output.

Finish with all-request/source/hash/count audits, independent raw controls,
owned-worker cleanup, a phase-two outcome/decision report, GitHub archival and
remote-SHA verification. If a desired improvement fails, preserve the result,
state the supported cause and the remaining falsifiable check. Experimental
completion does not depend on obtaining a favorable number.
