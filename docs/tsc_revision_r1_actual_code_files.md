# R1 Actual Result-Producing Code

This list excludes test files and private SSH/password helpers. Entry points were invoked by the experimental or analytical pipeline; helpers supplied functions used on those paths. Serving source is separately identified, not credited as new compiler code.

Current file hashes and exact historical main-client identity are in the machine-readable inventory. The main matrix used the archived pre-augmentation client; the current client adds only Turn-0 output logging.

## Executed Entrypoint

| File | Actual role |
|---|---|
| `scripts/run_tsc_revision_r1_batch.sh` | main matrix orchestration |
| `scripts/run_tsc_revision_r1_cell.sh` | fresh raw/ContractKV serving cells |
| `scripts/run_tsc_revision_r1_followup.sh` | zero-slack service and guard orchestration |
| `scripts/run_tsc_revision_qwen14_cost.sh` | TP2 cost supplement orchestration |
| `scripts/run_vllm_server.sh` | actual model server startup |
| `scripts/stop_vllm_server.sh` | owned server cleanup |
| `scripts/tsc_revision_build_inputs.py` | source-disjoint frozen input selection |
| `scripts/tsc_revision_live.py` | raw-reference attestation and actual free generation |
| `scripts/tsc_revision_qwen14_cost_live.py` | TP2 client entrypoint |
| `scripts/tsc_revision_qwen14_preflight.py` | frozen TP2 tokenizer/context capacity check |
| `scripts/tsc_revision_cell_manifest.py` | per-cell source/runtime/model/input identity |
| `scripts/tsc_revision_prepare_service.py` | frozen 20-session service input construction |
| `scripts/tsc_revision_zero_slack_live.py` | same-engine raw-reference service attestation |
| `scripts/tsc_revision_guard_probe.py` | live order-sensitive reject/zero-publication control |
| `scripts/tsc_revision_offline_audit.py` | archived full-cost and free-text analysis |
| `scripts/tsc_revision_baseline_audit.py` | matched native-baseline task-score analysis |
| `scripts/tsc_revision_input_layout_audit.py` | frozen-tokenizer positional displacement |
| `scripts/tsc_revision_registration_audit.py` | CPU registration trust-boundary audit |
| `scripts/tsc_revision_summarize.py` | paired performance, token quality, joint-session bootstrap |
| `scripts/tsc_revision_diagnostics.py` | raw-repeat, cost, rejection and root-cause diagnostics |
| `scripts/tsc_revision_service_summary.py` | actual zero-slack service/quality/log aggregation |
| `scripts/audit_tsc_revision_r1_completion.py` | required-cell/count/hash/invariant closure |
| `scripts/tsc_revision_source_inventory.py` | source and serving patch provenance |
| `scripts/tsc_revision_report.py` | final evidence-bounded X1-X7 report |
| `scripts/tsc_revision_package_raw.py` | verified raw-evidence archive and file hashes |
| `scripts/tsc_revision_resource_transition.py` | authorized GPU-resource transition audit |
| `scripts/install_vllm_v1_ephemeral_shadow_hook.py` | install ephemeral transactional shadow hooks |
| `scripts/install_vllm_v1_prefix_metrics_probe.py` | install real prefix/physical-block observations |

## Result Path Helper

| File | Actual role |
|---|---|
| `scripts/phase13b_fresh_policy_quality_replay.py` | build_case: benchmark-derived segments |
| `scripts/phase22_llama_layout_ladder.py` | stable-segment expansion and frozen L0-L3 ordering |
| `scripts/phase12f_real_vllm_caposc_replay.py` | ordered segment rendering |
| `scripts/phase20a_official_quality.py` | frozen official-compatible task scoring |
| `scripts/phase17_live_common.py` | actual raw generation, tokenizer and verifier HTTP clients |
| `scripts/phase16r_verifier_live.py` | actual token IDs and raw-margin extraction |
| `scripts/contractkv_verifier.py` | EOS separation and in-engine compact strict-path report |
| `scripts/contractkv_pstp.py` | stable/LCP commit boundary and transaction metadata |
| `scripts/contractkv_quiescence.py` | scheduler shadow-work admission |
| `scripts/contractkv_shadow_parking.py` | scheduler shadow request parking/resumption |
| `scripts/tsc_real_task_open_loop.py` | frozen Poisson trace, service timing and task scores |
| `scripts/tsc_service_template_quality_live.py` | template prompt compilation and scope records |
| `scripts/contractkv_certificate_binding.py` | signed generation/runtime/manifest scope check |
| `scripts/phase12e_cache_aware_posc.py` | service prompt compiler and segment-prefix ledger |
| `scripts/phase14c_run_full_pool_quality_jobs.py` | task-specific prompt messages |
| `scripts/phase12_prefix_cache_ab.py` | real sync/async streaming clients and percentiles |
| `scripts/summarize_submission_supplement.py` | percentile definition |
| `scripts/summarize_llama_sota_matrix.py` | archived matched-baseline joins and official scores |

## Actual Serving Engine Source

| File | Actual role |
|---|---|
| `third_party/vllm-contractkv-tsc-r1/vllm/entrypoints/openai/api_server.py` | compact attestation/transaction/metrics path |
| `third_party/vllm-contractkv-tsc-r1/vllm/v1/core/sched/scheduler.py` | compact attestation/transaction/metrics path |
| `third_party/vllm-contractkv-tsc-r1/vllm/v1/engine/__init__.py` | compact attestation/transaction/metrics path |
| `third_party/vllm-contractkv-tsc-r1/vllm/v1/engine/async_llm.py` | compact attestation/transaction/metrics path |
| `third_party/vllm-contractkv-tsc-r1/vllm/v1/request.py` | compact attestation/transaction/metrics path |
