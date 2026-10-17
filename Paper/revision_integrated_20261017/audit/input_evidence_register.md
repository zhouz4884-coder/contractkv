# Supplementary evidence register — text revision 1

This register identifies the source of each substantive result used in the rewritten manuscript. It is an editorial provenance index, not a claim that experiments were rerun in this writing session. Repository references are pinned to commit `9bf891af62dd7cc424c6429c5c09277d0911c549`. The submitted manuscript baseline is the uploaded 25 July 2026 ZIP, not the earlier repository PDF.

## A01 — Abstract; I; VI-B; IX
Primary full-wall multipliers 1.619/1.109/1.070; Qwen mean readiness -43.87%

Evidence: [results/tsc_revision_r4/input_fidelity_validation_v1/analysis/performance_comparison_v1.csv](https://github.com/zhouz4884-coder/contractkv/blob/9bf891af62dd7cc424c6429c5c09277d0911c549/results/tsc_revision_r4/input_fidelity_validation_v1/analysis/performance_comparison_v1.csv)

Independent six sources, three models, three process repetitions; closed-loop two-request waves; throughput all business, readiness future only.

## A02 — Abstract; VI-D; IX
1,296 compiled future pairs, 0 output-ID differences

Evidence: [docs/tsc_revision_phase3_fidelity_validation_results_zh.md](https://github.com/zhouz4884-coder/contractkv/blob/9bf891af62dd7cc424c6429c5c09277d0911c549/docs/tsc_revision_phase3_fidelity_validation_results_zh.md)

Do not interpret as 1,296 independent source templates or universal equivalence. Full-route changes separately reported.

## A03 — Abstract; VI-B/G; IX
Separate Qwen cohort: original throughput 1.80266; adapted 1.06982

Evidence: [docs/tsc_revision_phase3_cost_repair_results_zh.md](https://github.com/zhouz4884-coder/contractkv/blob/9bf891af62dd7cc424c6429c5c09277d0911c549/docs/tsc_revision_phase3_cost_repair_results_zh.md)

Separate six-source cohort; shared raw control for original/adapted, not independent sums.

## B01 — II-B; Table I
New stable-body / native-total-hit / stable-body-recovery ratios

Evidence: [docs/tsc_revision_table_I_reconstruction_zh.md](https://github.com/zhouz4884-coder/contractkv/blob/9bf891af62dd7cc424c6429c5c09277d0911c549/docs/tsc_revision_table_I_reconstruction_zh.md)

Three different denominators. New actual-ID reconstruction replaces, but does not recover, old 85.0/2.4 values.

## B02 — II-A
Azure history and query precede source text

Evidence: `Azure-Samples/azure-search-openai-demo`, commit `558ffd397eddcfe4da5c85ebc285796b367eb9b2`, `app/backend/approaches/promptmanager.py` and `prompts/chat_answer.user.jinja2`.

Fixed external code revision 558ffd397eddcfe4da5c85ebc285796b367eb9b2; establishes a possible application order, not production frequency.

## C01 — III; IV-C/E; V-A
Deployment compiled-path witness vs first raw business witness; O(T+U) state/O(U) decisions

Evidence: [docs/tsc_revision_phase3_scope_amortization_audit_zh.md](https://github.com/zhouz4884-coder/contractkv/blob/9bf891af62dd7cc424c6429c5c09277d0911c549/docs/tsc_revision_phase3_scope_amortization_audit_zh.md)

No automatic dual-mode endpoint or independently signed second certificate is claimed.

## C02 — IV-C; Algorithm 1
Single selected candidate, one GPU attempt, raw .0625/candidate-EOS .125 checks

Evidence: [scripts/tsc_revision_r2_admission.py](https://github.com/zhouz4884-coder/contractkv/blob/9bf891af62dd7cc424c6429c5c09277d0911c549/scripts/tsc_revision_r2_admission.py)

Implementation also requires complete margins and positive aligned commit. Scope heuristic defined separately.

## C03 — IV-C
At most 16 normalized words, non-abstaining literal-or-raw-margin eligibility

Evidence: [scripts/tsc_revision_r4_policy_v2.py](https://github.com/zhouz4884-coder/contractkv/blob/9bf891af62dd7cc424c6429c5c09277d0911c549/scripts/tsc_revision_r4_policy_v2.py)

Finite empirical class; not semantic correctness or invariance proof.

## C04 — IV-D
PSTP exact-LCP block-aligned publication and fail-closed candidate cleanup

Evidence: [submission/contractkv_tsc.tex](https://github.com/zhouz4884-coder/contractkv/blob/9bf891af62dd7cc424c6429c5c09277d0911c549/submission/contractkv_tsc.tex)

Technical statement reconciled with uploaded 2026-07-25 Sections III-E/IV-C and later code/report evidence. Repository manuscript is not used as the submitted-version baseline.

## C05 — IV-F
Two-stage expected net benefit and separate fan-out waiting variant

Evidence: [scripts/tsc_revision_r4_cost_policy.py](https://github.com/zhouz4884-coder/contractkv/blob/9bf891af62dd7cc424c6429c5c09277d0911c549/scripts/tsc_revision_r4_cost_policy.py)

Analytical restatement of implemented features, not a new predictor or measured hard-tail bound.

## D01 — V-B; VI-C
Input repair with original whitespace, query/CODE_PREFIX protection and answer-blind cropping

Evidence: [docs/tsc_revision_phase3_task_fidelity_validation_zh.md](https://github.com/zhouz4884-coder/contractkv/blob/9bf891af62dd7cc424c6429c5c09277d0911c549/docs/tsc_revision_phase3_task_fidelity_validation_zh.md)

Paired input ablation also changes contiguous segment rendering, not only input length.

## D02 — VI-C; Table IV
30/360 to 112/360 compiled; 1.03859 to 1.11675 throughput

Evidence: [results/tsc_revision_r4/input_fidelity_development_comparison_v1.json](https://github.com/zhouz4884-coder/contractkv/blob/9bf891af62dd7cc424c6429c5c09277d0911c549/results/tsc_revision_r4/input_fidelity_development_comparison_v1.json)

Four observed sources, one process per cell; absolute quality gain belongs to input repair.

## D03 — VI-B; Table III
Actual business/qualification new-prefill counts

Evidence: [docs/tsc_revision_phase3_fidelity_validation_results_zh.md](https://github.com/zhouz4884-coder/contractkv/blob/9bf891af62dd7cc424c6429c5c09277d0911c549/docs/tsc_revision_phase3_fidelity_validation_results_zh.md)

Initial scheduler counters; token counts do not imply a pure GPU-time reduction.

## D04 — VI-D; Table V
Raw-positive compiled future counts Q684/M258/L90; full-route decreases 0/1/3

Evidence: [results/tsc_revision_r4/input_fidelity_validation_v1/fidelity_utility_audit_v1.json](https://github.com/zhouz4884-coder/contractkv/blob/9bf891af62dd7cc424c6429c5c09277d0911c549/results/tsc_revision_r4/input_fidelity_validation_v1/fidelity_utility_audit_v1.json)

Positive score is not complete correctness; Mistral decline is initial, Llama declines future.

## D05 — VI-D
R4 2,442 compiled no IDs/score change; 33 L0 decreases

Evidence: [docs/tsc_revision_supplementary_experiment_record_zh.md](https://github.com/zhouz4884-coder/contractkv/blob/9bf891af62dd7cc424c6429c5c09277d0911c549/docs/tsc_revision_supplementary_experiment_record_zh.md)

Historical-adapter five-family cohort is distinct from preserved-input validation.

## D06 — VI-D
108/3672 earlier admitted decreases and doc99 metadata counterexample

Evidence: [docs/tsc_revision_supplementary_experiment_record_zh.md](https://github.com/zhouz4884-coder/contractkv/blob/9bf891af62dd7cc424c6429c5c09277d0911c549/docs/tsc_revision_supplementary_experiment_record_zh.md)

Failure occurred within old permitted scope. Retained, not reclassified as outside scope.

## D07 — VI-D
Long natural-stop sequences 642/769/578 tokens; failed 224-item condition

Evidence: [docs/tsc_revision_phase2_long_format_results_zh.md](https://github.com/zhouz4884-coder/contractkv/blob/9bf891af62dd7cc424c6429c5c09277d0911c549/docs/tsc_revision_phase2_long_format_results_zh.md)

Different declared item counts; actual output lengths, not max-token caps.

## E01 — VI-E
Two 20-case sets, ten unsafe layouts each rejected, zero candidate publication

Evidence: [docs/tsc_major_revision_r1_results.md](https://github.com/zhouz4884-coder/contractkv/blob/9bf891af62dd7cc424c6429c5c09277d0911c549/docs/tsc_major_revision_r1_results.md)

Controlled bad-layout evidence distinct from default accepted serving workload.

## E02 — VI-E/F
D1/D2 goodput; 125 to 5 registrations; 25.05 to 3.24 ms exposed cost

Evidence: uploaded `contractkv_tsc_submission_2026-07-25.zip`, `contractkv_tsc.tex`, original Sections VI-E and VII.

Legacy deployment-qualified protocol; not raw-query qualification cost. Raw source-data reproduction was not rerun in this writing session.

## E03 — VI-F; Table VI
Separate zero-slack net-TTFT results 17.50/-2.84/7.69/10.59%

Evidence: [docs/tsc_major_revision_phase1_summary_zh.md](https://github.com/zhouz4884-coder/contractkv/blob/9bf891af62dd7cc424c6429c5c09277d0911c549/docs/tsc_major_revision_phase1_summary_zh.md)

Separate supplemental protocols, not exact retrospective correction of all old clocks.

## E04 — VI-F
30 common HotpotQA sessions; 2430 pairs; prefill48.05/40.69/38.38%; macro CI

Evidence: [docs/tsc_major_revision_phase1_summary_zh.md](https://github.com/zhouz4884-coder/contractkv/blob/9bf891af62dd7cc424c6429c5c09277d0911c549/docs/tsc_major_revision_phase1_summary_zh.md)

Old input protocol and mean-effect interval; not architecture-wide predictive interval.

## E05 — VI-G; Table VII
Cost support failure: HP 13.9–14.6K versus observed maximum ~6880; 18 useful decisions rejected

Evidence: [docs/tsc_revision_phase3_cost_repair_results_zh.md](https://github.com/zhouz4884-coder/contractkv/blob/9bf891af62dd7cc424c6429c5c09277d0911c549/docs/tsc_revision_phase3_cost_repair_results_zh.md)

Negative variant retained; not adopted as default.

## E06 — VI-H; Table VIII
138 diagnostic requests, 4 qualifications, 13 traced native evictions; 12/12 immediate hits

Evidence: [docs/tsc_revision_residency_results_20261017_zh.md](https://github.com/zhouz4884-coder/contractkv/blob/9bf891af62dd7cc424c6429c5c09277d0911c549/docs/tsc_revision_residency_results_20261017_zh.md)

Known-source instrumented diagnosis, neither new held-out sample nor speed comparison.

## E07 — VI-I
CacheBlend224 decreases331 increases; own-native mean scores; ContractKV2/0

Evidence: [docs/tsc_revision_supplementary_experiment_record_zh.md](https://github.com/zhouz4884-coder/contractkv/blob/9bf891af62dd7cc424c6429c5c09277d0911c549/docs/tsc_revision_supplementary_experiment_record_zh.md)

Distinct native runtimes. No causal 112x safety or 2.18pp speed ranking.

## F01 — VIII-B
Manifest 9 CPU cases /7 rejects; trusted semantic mislabel accepted; timing defense absent

Evidence: [docs/tsc_revision_reviewer_experiment_response_zh.md](https://github.com/zhouz4884-coder/contractkv/blob/9bf891af62dd7cc424c6429c5c09277d0911c549/docs/tsc_revision_reviewer_experiment_response_zh.md)

CPU helper not integrated endpoint; signed deployment/PSTP tests have separate scopes.
