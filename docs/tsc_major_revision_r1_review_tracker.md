# Major Revision: Reviewer-to-Evidence Tracker

Latest evidence update (2026-10-16): the historical Phase-1/2 entries below are
preserved. The current 36-item experimental response record is
`docs/tsc_revision_reviewer_experiment_response_zh.md`, and the consolidated
experiment record is `docs/tsc_revision_supplementary_experiment_record_zh.md`.
R4 closed-loop36 is complete; fixed-arrival5/54 remains explicitly partial.
The four input-fidelity development cells are complete, with a retained p99
regression. Independent faithful-input validation has not started and awaits
the user's scientific choice. Neither document claims submission readiness.

Readiness: **Phase-1 and the authorized Phase-2 experiment round complete and archived;
remaining quality/economics/tail targets documented; manuscript not ready to submit**.
The submitted manuscript is preserved. This tracker does not claim that the
manuscript or response letter has already been revised.

Task mode: **completed experimental supplements and targeted optimization** for a **major revision**. Response-package readiness
is **draft_with_placeholders**, because manuscript locations and text revisions
are not yet assigned. Experimental completion and
submission readiness are separate states.

Phase-1 closure is summarized in `docs/tsc_major_revision_phase1_summary_zh.md`.
R1R local and remote audits confirm 45/45 main cells (28,350 futures), 9/9
long-output cells (135 actual generations), and 9/9 known-case policy cells
(108 futures). All three archives have per-member transport verification;
remote closure verifies all 83 prospective source/input checks and no owned
resident GPU process. Two compiled quality regressions remain in the new main
cohort. Targeted optimization is the separately authorized second phase.

Phase-2 closure is summarized in `docs/tsc_revision_phase2_summary_zh.md`.
Two independently frozen cohorts cover 90 cells and 67,500 actual business
generations. The first cohort retains seven compiled material score drops;
the amended second cohort retains three drops from one Qwen NarrativeQA unit.
The second cohort has 4,965 compiled paired futures, including 3,612 fan-out
compiled futures with no score or output-ID change. Its cold-session
full-wall gains are 1.074/1.006/1.001x raw and fan-out gains are
1.833/1.101/1.067x. Stable cold gains and common p99 improvement are not
established. All three models have separately declared >512-token correct,
admitted long-output conditions; Llama's 224-item stress failure is retained.
Eleven completed studies have local per-member verification/recomputation,
2,005 archive members including repeated snapshots and 22 rehashed parts.
Remote closure checks 729 Phase-2 source/snapshot commitments, six dispatch
commitments, the original 83 checks and no owned resident GPU worker.
Residuals and proposed next checks are in
`docs/tsc_revision_phase2_next_stage_issues_zh.md`; a new GPU round has not begun.

The decision letter is identified by SHA256
`e5b12656164650d7d9d13fd9377ded67b346b7963d5893735d84354173fea03d`.
The original comments and a line-to-ID map are retained locally; the public
tracker uses concern summaries. The strategy is to accept the requested
experiments/analyses, preserve counterexamples, and soften claims when the
evidence only supports a bounded scope. No unseen manuscript line numbers or
completed text changes are implied here.

| ID | Concern | Evidence/action | Current state |
|---|---|---|---|
| E1 | Submit revision and point-by-point response by 2026-12-13 | Revised manuscript, separate response and verified upload | after experiment closure |
| E2 | Include author biographies and complete required manuscript parts | Obtain accurate author-supplied biographies | author facts needed later |
| E3 | Supplement/appendices separate | Keep supplementary files separate | submission packaging later |
| E4 | EIC prohibits colored/bold/italic change marks; AE asks colored changes | Prepare clean manuscript and location-specific change list; resolve submission-format conflict | unresolved format instruction |
| E5 | Maintain journal size limits | Compress duplicated methods/protocol prose rather than shrink figures or omit key evidence | manuscript stage |
| AE1 | Clarify component novelty versus end-to-end integration | Cross-reference R2.1/R2.5; separate known primitives from scoped publication governance | positioning/manuscript stage |
| AE2 | Certification beyond reordering; workloads, free generation and overhead | Cross-reference R1.2/R1.4 and R3.2/R3.3; use measured evidence with failures retained | experiments complete; bounded positive results and residual failures documented |
| AE3 | Fair and consistent baseline interpretation | Cross-reference R1.1/R1.3; native matched deltas and absolute operating points | analysis complete; manuscript changes pending |
| AE4 | Manifest, isolation and certification limitations | Cross-reference R1.5/R1.6; CPU and live boundaries kept explicit | evidence/limitations documented; manuscript changes pending |
| AE5 | Clarity, reproducibility and related work | Cross-reference R1.11/R1.12/R2.1/R2.2/R2.3 | reproducibility evidence available; text/citation work pending |
| R1.1 | Headline ratios and 92.90 vs 92.62 scope | Lead with all-workflow band; identify each independent service cell and absolute D0 operating point | manuscript stage |
| R1.2a | Common scope beyond RULER | X1: identical frozen 30-session HotpotQA scope, three models/repeats, all fallbacks retained | completed: 2430 paired futures; three-model effects and zero-slack uncertainty reported |
| R1.2b | Narrow macro CI versus model spread | Fixed-model estimand explanation; joint source-session bootstrap across models | completed: joint-session intervals in R1 report; not an architecture-population interval |
| R1.3a | Different stacks do not support performance superiority | Matched native baseline deltas; no causal 2.18% cross-stack claim | audit completed |
| R1.3b | Explain CacheBlend regression rate and asymmetry | 9000 archived matched pairs; mean changes, improvements and threshold sensitivity; original paper reporting comparison | completed and archived; cross-runtime superiority/112x causal safety claims not supported |
| R1.4a | Certified-prefix free-running divergence | X2: actual token IDs, first divergence, score difference, admitted/fallback and raw-repeat controls | complete: original 108 compiled drops retained; new cohort has 2/8595 compiled drops; four selected old failure units reproduce and are protected in the new combined control |
| R1.4b | Explicit certified output horizon | Original family budgets and newly bound 512-token condition; actual length/stop distribution and positions beyond the recorded witness length | complete: original 216/3672 outputs exceed their witness length; controlled Qwen/Mistral compiled outputs reach 646/769 actual tokens; Llama rejects and has no compiled long positive evidence |
| R1.5 | Manifest correctness is a trust boundary | Dedicated ownership/declaration/hash audit; explicitly show trusted semantic mislabelling is not detected by hashing | nine CPU cases completed; helper is not wired to the live endpoint; manuscript subsection pending |
| R1.6 | Prefix timing side channel | Explicit limitation: authorization does not eliminate shared-prefix timing leakage | documented; no timing-defense claim |
| R1.7 | 325000 stress operations are CPU state-machine work | Qualify or remove abstract number; retain live/CPU distinction | manuscript stage |
| R1.8 | Small KV pool and datacenter-scale implications | Prominent 2386-block original pool, active concurrency vs registered tenants, working-set sweep discussion | existing data; manuscript stage |
| R1.9 | Raw fallback and 50% coverage deserve prominence | Include the original flagship Llama 40% raw-route share, direct L0 versus failed registration costs/quality, and actual routing denominators | archived audit completed; source-specific interpretation needed |
| R1.10 | Table V overflow | Re-render after text revision | layout stage |
| R1.11 | Worked example and terminology load | One concrete compile/certify/promote/reuse request; consolidate repeated method/scope prose | manuscript stage |
| R1.12 | Make space for the requested additions | Compress III-A–III-C; merge overlapping IV-B/IV-D scope prose; remove Table II protocol duplication and group related-work acknowledgements | manuscript stage; no compression claimed yet |
| R2.1 | Prior-work progression/table | Compare reuse primitive, behavioral admission, authorization/lifecycle and publication governance | literature/manuscript stage |
| R2.2 | Model/task citations and published venues | Verify model cards, benchmark papers and COLM 2024 RULER citation | literature stage |
| R2.3 | Package versions for reproducibility | Per-cell package/source/model/input manifests and original runtime inventory | complete: R1 78 manifests/51-file inventory; R1R 63-file code inventory, all 83 source/input checks, verified main and known-case archives plus local rerun audits |
| R2.4 | Artifact link as footnote | Move public URL to a footnote without removing artifact availability | manuscript stage |
| R2.5 | Individual versus integration novelty | Explicitly distinguish known primitives from scoped service-template certification and transactional shared-state admission | manuscript stage |
| R2.6 | Input-level prompt displacement | Exact frozen-tokenizer rendered prompt/offset analysis: 4695 segments | completed |
| R3.1 | Raw order per family and realism | Document controlled SYS/OBS/context/query ordering and benchmark-derived trace construction; distinguish it from production frequency evidence | PARTIAL: input audit complete; neither this trace nor repeated-query fan-out measures production ordering/query-repeat prevalence |
| R3.2 | Count full verification at zero slack beside Table III | Archived full-clock gaps marked unavailable; fresh complete registration timing, zero-slack service and 14B TP2 cost supplement | completed and archived; R1R now measures readiness and full-wall costs directly with no slack subtraction |
| R3.3 | Value beyond D1 and rejection case | Preserve speed relative to D1 while measuring rejection/quality/zero publication on identical bad candidates | completed: 10/10 genuinely bad layouts rejected; zero rejected publication; fresh post-decision outputs retain raw scores |
| R3.4 | 4.81x point/CI, CPU stress, greedy restriction | State 80%-load point and CI; separate CPU stress; explicit greedy generation scope | manuscript stage |
| R3.5 | Relevant additional references | Verify and add relevant serving/scheduling/security/SLA work; do not substitute citations for experimental answers | literature stage |

Experimental task IDs X1-X7 and the full completion requirements are defined in
`docs/tsc_major_revision_r1_experiment_plan.md`. A network observation failure
does not establish that a background job stopped. Original PID/process state and
complete-cell source hashes must be checked before resuming any cell.

## Evidence and proposed response actions

The action labels below describe the response strategy. Text revisions remain
pending until a revised manuscript supplies real section/table locations.

| Concern IDs | Type / severity | Proposed action | Inspectable evidence | Remaining boundary |
|---|---|---|---|---|
| R1.2a / AE2 | evidence / major | ACCEPT_EXPERIMENT | `results/tsc_revision_r1/fresh_paired_performance_v1.csv`; R1 report X1 | Common HotpotQA improves prefill; zero-slack macro CI crosses zero |
| R1.2b | statistical / major | ACCEPT_ANALYSIS + SOFTEN_CLAIM | `results/tsc_revision_r1/common_hotpot_shared_cluster_ci_v1.csv` | Fixed three-model estimand; not an architecture-population interval |
| R1.4a / AE2 | evidence / major | ACCEPT_EXPERIMENT + SOFTEN_CLAIM | `fresh_token_quality_summary_v1.csv`, `material_quality_drop_cases_v1.csv` under R1; R1R `validation/summary/` and `known_counterexamples/` | Original failures retained; controlled query-catalog repair protects selected old cases but has two new compiled regressions; not universal future equivalence |
| R1.4b | evidence / major | ACCEPT_EXPERIMENT + SOFTEN_CLAIM | R1 horizon CSVs; R1R `long_horizon/summary/` including actual-ID/metric audit | Actual >512 outputs established for two models in a controlled array task; Mistral differs from future raw and Llama lacks a compiled positive; extra witness positions remain uncertified |
| R3.2 | evidence / major | ACCEPT_ANALYSIS + ACCEPT_EXPERIMENT | R1 `historical_full_cost_by_repeat_v1.csv`, `fresh_cost_decomposition_v1.csv`; R1 report X3 | Missing historical clocks stay unavailable; live readiness/full-wall clocks and offline slack accounting are separate |
| R3.3 | evidence / major | ACCEPT_EXPERIMENT + CLARIFY_EXISTING | R1 `guard_probe_qwen_v1.jsonl`, `guard_probe_qwen14_actual_v2.jsonl`; R1 report X4 | D1 is a latency reference; D2 adds rejection/publication governance rather than guaranteed speed over D1 |
| R1.5 / AE4 | scope / major | ACCEPT_ANALYSIS + SOFTEN_CLAIM | R1 `registration_manifest_cases_v1.csv` and `registration_manifest_summary_v1.json` | Standalone CPU audit; trusted semantic mislabelling remains undetected |
| R1.6 / AE4 | scope / major | SOFTEN_CLAIM | Explicit limitation in R1 report X5 and R1R reproduce notes | No timing-channel defense or adversarial public-tenant endpoint validation |
| R1.3 / AE3 | interpretation / major | ACCEPT_ANALYSIS + SOFTEN_CLAIM | R1 `matched_baseline_audit_manifest_v1.json`; R1 report X6 | No 2.18% cross-stack causal speed claim or 112x causal safety ranking |
| R2.3 / AE5 | reproducibility / minor | ACCEPT_ANALYSIS + ACCEPT_TEXT | R1 and R1R runtime/source inventory, local/remote completion audits and verified archives | Experimental evidence complete; manuscript citation/version placement remains pending |
| R2.6 / R3.1 | methodology / major | ACCEPT_ANALYSIS + PARTIAL | R1 `segment_token_displacement_v1.csv` and summary; R1 report X6 | Input displacement is measured; production workload prevalence is not |

All other rows above are manuscript, citation or formatting actions. They are
not silently marked experimentally complete or submission-ready. E3 also
records an instruction conflict with Reviewer 2's supplementary-material
questionnaire preference: preserve the editor's separate-document requirement
when preparing the eventual package. E4 retains the separate colored-change
conflict for final format resolution.

## 中文核对

- 原 R1 的负结果、fallback 分母和缺失历史时钟必须继续保留。
- R1R 的 query 绑定、统一下降和宽辅助阈值属于受控变体，不能替换原论文完整策略结果。
- 每项实验证据齐全后，再填写真实修稿位置；目前没有虚构页码、行号或新增图表编号。
- 作者简介属于后续 `AUTHOR_INPUT_NEEDED`，不妨碍继续完成当前实验目标。
