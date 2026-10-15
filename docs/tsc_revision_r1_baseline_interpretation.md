# R1 Baseline Comparison Interpretation

The comparison uses each system's native matched baseline. ContractKV's
reference is raw-order vLLM APC; CacheBlend's reference is the separator-only
LMCache runtime; the SGLang compiled-layout diagnostic uses raw RadixAttention.
These baselines differ in serialization and runtime. A 2.18% descriptive
absolute mean difference is not evidence of causal superiority across stacks.

The archived CacheBlend aggregate task score increases from 0.33321 to 0.33982,
while 9.956% of paired requests have score drops above 0.03. Mean score and
per-request regression frequency are different statistics; both must be shown.
The R1 audit retains improvements, ties, and regressions at 0.01/0.03/0.05.
It does not convert the two methods' rates into a causal "112x safer" claim.

The [original CacheBlend paper](https://arxiv.org/html/2405.16444v3), Sections
7.1-7.3, evaluates Mistral-7B, Yi-34B and Llama-70B using QA/summarization
datasets and aggregate F1/Rouge-L. It describes quality losses of about
0.01-0.03 and recomputation-ratio sensitivity. This does not report the
per-request >0.03 regression statistic on our Llama-3.1-8B multi-turn trace.
Our result therefore cannot be framed as a failed replication of their stated
aggregate-quality result. The workload/model/threshold differences and the
32-token LMCache compatibility configuration remain explicit.

Evidence: `results/tsc_revision_r1/matched_baseline_quality_thresholds_v1.csv`,
its request-pair CSV and source-hash manifest. The original source metadata is
verified as EuroSys 2025, DOI 10.1145/3689031.3696098. The publisher DOI fetch
failed in this audit; the primary authors' arXiv version identifies the venue
and DOI and supplies the evaluation details.
