# Major Revision: Reviewer-to-Evidence Tracker

Readiness: **R1 execution complete and archived; query-bound repair validation
in progress; manuscript not ready to submit**.
The submitted manuscript is preserved. This tracker does not claim that the
manuscript or response letter has already been revised.

| ID | Concern | Evidence/action | Current state |
|---|---|---|---|
| E1 | Submit revision and point-by-point response by 2026-12-13 | Revised manuscript, separate response and verified upload | after experiment closure |
| E2 | Include author biographies and complete required manuscript parts | Obtain accurate author-supplied biographies | author facts needed later |
| E3 | Supplement/appendices separate | Keep supplementary files separate | submission packaging later |
| E4 | EIC prohibits colored/bold/italic change marks; AE asks colored changes | Prepare clean manuscript and location-specific change list; resolve submission-format conflict | unresolved format instruction |
| E5 | Maintain journal size limits | Compress duplicated methods/protocol prose rather than shrink figures or omit key evidence | manuscript stage |
| R1.1 | Headline ratios and 92.90 vs 92.62 scope | Lead with all-workflow band; identify each independent service cell and absolute D0 operating point | manuscript stage |
| R1.2a | Common scope beyond RULER | X1: identical frozen 30-session HotpotQA scope, three models/repeats, all fallbacks retained | completed: 2430 paired futures; three-model effects and zero-slack uncertainty reported |
| R1.2b | Narrow macro CI versus model spread | Fixed-model estimand explanation; joint source-session bootstrap across models | completed: joint-session intervals in R1 report; not an architecture-population interval |
| R1.3a | Different stacks do not support performance superiority | Matched native baseline deltas; no causal 2.18% cross-stack claim | audit completed |
| R1.3b | Explain CacheBlend regression rate and asymmetry | 9000 archived matched pairs; mean changes, improvements and threshold sensitivity; original paper reporting comparison | completed and archived; cross-runtime superiority/112x causal safety claims not supported |
| R1.4a | Certified-prefix free-running divergence | X2: actual token IDs, first divergence, score difference, admitted/fallback and raw-repeat controls | R1 complete: changed-query counterexamples retained; query-bound repair validation running on new sources |
| R1.4b | Explicit certified output horizon | Original family budgets and newly bound 512-token condition; actual length/stop distribution | R1 complete but actual admitted outputs short; separate controlled actual-long-output supplement queued |
| R1.5 | Manifest correctness is a trust boundary | Dedicated ownership/declaration/hash audit; explicitly show trusted semantic mislabelling is not detected by hashing | nine CPU cases completed; manuscript subsection pending |
| R1.6 | Prefix timing side channel | Explicit limitation: authorization does not eliminate shared-prefix timing leakage | documented; no timing-defense claim |
| R1.7 | 325000 stress operations are CPU state-machine work | Qualify or remove abstract number; retain live/CPU distinction | manuscript stage |
| R1.8 | Small KV pool and datacenter-scale implications | Prominent 2386-block original pool, active concurrency vs registered tenants, working-set sweep discussion | existing data; manuscript stage |
| R1.9 | Raw fallback and 50% coverage deserve prominence | Direct L0 vs failed runtime registration costs and quality; audit observed routing rather than infer from coverage | archived audit completed; source-specific interpretation needed |
| R1.10 | Table V overflow | Re-render after text revision | layout stage |
| R1.11 | Worked example and terminology load | One concrete compile/certify/promote/reuse request; consolidate repeated method/scope prose | manuscript stage |
| R2.1 | Prior-work progression/table | Compare reuse primitive, behavioral admission, authorization/lifecycle and publication governance | literature/manuscript stage |
| R2.2 | Model/task citations and published venues | Verify model cards, benchmark papers and COLM 2024 RULER citation | literature stage |
| R2.3 | Package versions for reproducibility | Per-cell package/source/model/input manifests and original runtime inventory | R1 complete: 78 manifests, exact main source and 51-file result-code inventory; R1R freezes recorded |
| R2.4 | Artifact link as footnote | Move public URL to a footnote without removing artifact availability | manuscript stage |
| R2.5 | Individual versus integration novelty | Explicitly distinguish known primitives from scoped service-template certification and transactional shared-state admission | manuscript stage |
| R2.6 | Input-level prompt displacement | Exact frozen-tokenizer rendered prompt/offset analysis: 4695 segments | completed |
| R3.1 | Raw order per family and realism | Document controlled SYS/OBS/context/query ordering and benchmark-derived trace construction; distinguish it from production frequency evidence | input audit completed; source-pattern discussion pending |
| R3.2 | Count full verification at zero slack beside Table III | Archived full-clock gaps marked unavailable; fresh complete registration timing, zero-slack service and 14B TP2 cost supplement | completed and archived; R1R now measures readiness and full-wall costs directly with no slack subtraction |
| R3.3 | Value beyond D1 and rejection case | Preserve speed relative to D1 while measuring rejection/quality/zero publication on identical bad candidates | completed: 10/10 genuinely bad layouts rejected; zero rejected publication; fresh post-decision outputs retain raw scores |
| R3.4 | 4.81x point/CI, CPU stress, greedy restriction | State 80%-load point and CI; separate CPU stress; explicit greedy generation scope | manuscript stage |
| R3.5 | Relevant additional references | Verify and add relevant serving/scheduling/security/SLA work; do not substitute citations for experimental answers | literature stage |

Experimental task IDs X1-X7 and the full completion requirements are defined in
`docs/tsc_major_revision_r1_experiment_plan.md`. A network observation failure
does not establish that a background job stopped. Original PID/process state and
complete-cell source hashes must be checked before resuming any cell.
