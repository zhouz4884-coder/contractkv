# ContractKV

ContractKV compiles dependency-valid agent prompts into cache-friendly linear
layouts, verifies candidate behavior in the serving engine, and
transactionally publishes only certified stable prefixes. The final prototype
targets vLLM 0.10.2 and treats every certificate as an empirical attestation
with an explicit model, task, layout, content, policy, and observation or
qualification scope.

## Final paper path

- `scripts/contractkv_certificate_scope.py`: fail-closed certificate scope.
- `scripts/phase19b_end_to_end_live.py`: task-bearing live replay.
- `scripts/run_submission_repeats.sh`: paired three-repeat Qwen/Mistral run.
- `scripts/run_external_sglang_baseline.sh`: bounded SGLang radix baseline.
- `scripts/run_llama_qualified_replay.sh`: prospective Llama task-family replay.
- `scripts/run_physical_dedup_submission.sh`: 10/20-agent physical KV-block dedup.
- `scripts/generate_submission_package.py`: paper, appendix, and figures.
- `scripts/build_paper_artifact.py`: minimal SHA-256-audited artifact.

The scope semantics are frozen in
`docs/contractkv_certificate_validity_scope.md`. The final submission package
is generated under `submission/`, and the clean release under
`artifact/contractkv-paper-v1/`.

## Reproduction

```bash
bash scripts/run_submission_repeats.sh
bash scripts/install_sglang_external_baseline.sh
bash scripts/run_external_sglang_baseline.sh
bash scripts/run_llama_qualified_replay.sh
bash scripts/run_physical_dedup_submission.sh
python scripts/generate_submission_package.py
python scripts/build_paper_artifact.py
```

Models, datasets, environments, caches, raw request logs, and server logs stay
on the 8 TB data volume. Git contains source, lightweight summarized results,
documentation, and manifests only.
