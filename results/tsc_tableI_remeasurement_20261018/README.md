# Independent structural survey for ContractKV Table I

This is a new, preregistered measurement. It does not recover the original
Table-I numeric lineage and does not fit its parameters to those old values.

The immutable primary registration is commit
`40e16ba06af8caef23fbf6a458480655ef881d7d`; `freeze.json` has SHA256
`a9a1788b6745a194a29c6c1a1edfea679fbe9351c6b8e06483bc59741c5d4bf3`.
`pre_forward_receipt_v1.json` records remote-commit verification and server time
before the first source request. Primary scripts, input files and model registry
are copied under `source_snapshot/` with byte hashes.

## Evidence classes

- `upstream_v2/`: visible historical file reads, returned document excerpts and
  schema/command audits. These establish access to files, not original
  measurements or an author's intent. No private reasoning is exported.
- `inputs_v1/`: all 125 selected sources, original and packed text, omissions,
  protected-field and tokenizer checks. Synthetic histories in CPU preflight
  are only shape/window checks. Actual survey histories use generated answers.
- `native_preflight_v1.json`: independent native-runtime overlay and full model
  hash checks. Two modified installed sources were restored in the overlay to
  official v0.10.2 bytes matching RECORD; the original environment was untouched.
- `cells/raw_native_r*/`: measured IDs/text/cache counts, native controls,
  completion hashes, progress and logs. The primary population is turns 1-9;
  turn 0 is cold and reported separately.
- `analysis_v1/summary_v1.json`: frozen primary aggregates and registered-ID-cluster
  bootstrap intervals, retained alongside the context-cluster addendum below.
  The five-family mean and global token-pooled ratio are
  different statistics. Repeated requests/tenants are not independent sources.
- `analysis_v1/independent_integrity_v1.json`: additional integrity checks of
  actual history, stable text and an offline unbounded-prefix diagnostic. This
  extra audit was documented during execution; it does not change the primary
  estimator. Offline bounds are not measured native cache hits.
- `auxiliary_existing_six_source_v1.json`: separately restored six-source,
  three-model raw-cache evidence. It has its own protocol and declared stable
  spans, and must not be pooled with this survey or used to authenticate old
  Table-I values.
- `source_frame/`: lossless candidate-pool archive. Its uncompressed SHA256 was
  registered before source forwards; compression was retained afterward. The
  original pool includes reference fields, which are not used in source ranking,
  packing or model input generation.
- `tokenizer_snapshot/`: the registered tokenizer/config bytes, without model
  weights, plus the model license. It supports offline CPU reanalysis.

## Measurement scope

Five families x 25 registered task records x 10 controlled turns x 3 fresh processes
give 3,750 source requests, including 3,375 future requests. Six literal
infrastructure controls are separate. The task/source is fixed within a session;
ten query wrappers and real accumulated answer history are not ten independent
natural questions or a production trace. The 125 registered IDs represent 114
exact original-context clusters (25/25/15/24/25 across the five families).
All 25 NarrativeQA records and five Qasper records have contexts seen among
earlier excluded IDs. This is not an entirely unseen-document validation.

The frozen primary ID-cluster intervals are retained. An input-driven addendum,
recorded during execution before final aggregation, also computes original-
context-cluster intervals without replacing records or changing point estimates.
See `context_cluster_addendum_v1.json` and
`analysis_v1/context_cluster_stats_v1.json`. Exact text uniqueness is not proof
of semantic independence.

Native vLLM APC is the measured system. There is no CALC, certification, PSTP,
ContractKV speedup or end-to-end SLO-capacity claim in this experiment. In
particular, evolving generated histories do not establish qualification coverage
for the paper's conservative service protocol. Source identity, input packing,
generation settings and the primary statistical rule remain fixed after the
registration.

`stable_ratio_pct` divides declared stable body tokens by all actual input
tokens. `stable_native_recovery_pct` divides actual cache hits on stable body by
stable body tokens. `all_native_hit_pct` divides all native hits, including
mutable history or framing, by all input tokens. These quantities cannot be
interchanged.

## Reanalysis without model inference

Keep the original outputs. To rerun the frozen primary aggregation, copy
`freeze.json`, `inputs_v1/` and the three completed `cells/` to a new study
directory without `analysis_v1/`, retaining repository scripts/config paths.
Run the following with Python and the frozen Qwen tokenizer files:

```powershell
python -B scripts/tsc_tableI_analyze_survey_v1.py --root PATH_TO_NEW_STUDY_COPY --tokenizer PATH_TO_QWEN3_TOKENIZER
python -B scripts/tsc_tableI_verify_final_v1.py --root PATH_TO_NEW_STUDY_COPY
```

The primary analyzer uses `transformers==4.55.2` and its fast tokenizer, with
PyTorch disabled. The extra integrity check uses Python's standard library.
Neither command sends model requests. The original sources/configs referenced
by `freeze.json` must retain their registered hashes. Do not overwrite the
archived results or silently relax a failed check.
