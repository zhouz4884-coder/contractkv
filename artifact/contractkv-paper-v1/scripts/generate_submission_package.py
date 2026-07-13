#!/usr/bin/env python3
"""Generate the paper-facing ContractKV submission package from frozen results."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def pct(value: str | float) -> str:
    return f"{float(value) * 100:.2f}%"


def f(value: str | float) -> str:
    return f"{float(value):.2f}"


def make_figure(rows: list[dict[str, str]], output: Path) -> None:
    import matplotlib.pyplot as plt

    metrics = [
        ("net_mean_ttft_reduction", "Net mean TTFT reduction"),
        ("p95_ttft_reduction", "p95 TTFT reduction"),
        ("new_prefill_reduction", "New-prefill reduction"),
    ]
    models = [row["model"] for row in rows]
    colors = ["#2374AB", "#E07A3F"]
    fig, axes = plt.subplots(1, 3, figsize=(9.2, 3.0), constrained_layout=True)
    for axis, (key, title) in zip(axes, metrics):
        values = [float(row[f"mean_{key}"]) * 100 for row in rows]
        low = [value - float(row[f"bootstrap95_low_{key}"]) * 100
               for value, row in zip(values, rows)]
        high = [float(row[f"bootstrap95_high_{key}"]) * 100 - value
                for value, row in zip(values, rows)]
        axis.bar(models, values, color=colors[:len(models)], width=.62,
                 yerr=[low, high], capsize=4, linewidth=.6, edgecolor="#222222")
        axis.axhline(0, color="#333333", linewidth=.7)
        axis.set_title(title, fontsize=9)
        axis.set_ylabel("Reduction (%)", fontsize=8)
        axis.tick_params(axis="both", labelsize=8)
        axis.grid(axis="y", alpha=.22, linewidth=.6)
        for index, value in enumerate(values):
            axis.text(index, value + max(high[index], 0) + 1.2,
                      f"{value:.1f}", ha="center", va="bottom", fontsize=8)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output.with_suffix(".png"), dpi=240)
    fig.savefig(output.with_suffix(".pdf"))
    plt.close(fig)


def external_text(path: Path) -> tuple[str, str]:
    if not path.exists():
        return (
            "The isolated external SGLang environment could not be completed within the frozen run; no external result is claimed.",
            "not_available",
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    comparisons = {row["model"]: row for row in data["comparisons"]}
    rows = []
    for row in data["matrix"]:
        peak = row["peak_kv_blocks"]
        if str(peak).startswith("unavailable"):
            slots = row.get("peak_kv_token_slots")
            peak = (f"{float(slots):.0f} token slots" if slots not in {None, ""} and
                    not str(slots).startswith("unavailable") else "unavailable")
        else:
            peak = f"{float(peak):.0f} blocks"
        rows.append(
            f"| {row['model'].title()} | {row['cell']} | {row['runtime']} | "
            f"{f(row['mean_ttft_ms'])} | {f(row['mean_p95_ttft_ms'])} | "
            f"{f(row['mean_prompt_tokens'])} | {f(row['mean_prefix_hit_tokens'])} | "
            f"{f(row['total_observed_new_prefill_tokens'])} | "
            f"{f(row['mean_wall_slo_goodput'])} | {f(row['mean_task_score'])} | {peak} |"
        )
    table = "\n".join([
        "| Model | Cell | Runtime | Mean TTFT ms | p95 TTFT ms | Input tokens | Prefix-hit tokens | Observed new-prefill total | SLO req/s | Task score | Peak KV |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        *rows,
    ])
    text = (
        "The B1-B4 matrix uses identical model-specific traces, concurrency, "
        "output limits, dtype, and three fresh processes. On SGLang, the "
        f"offline frozen safe layout reduces mean TTFT versus raw RadixAttention by "
        f"{pct(comparisons['qwen']['b4_mean_ttft_reduction_vs_b2'])} for Qwen and "
        f"{pct(comparisons['mistral']['b4_mean_ttft_reduction_vs_b2'])} for Mistral; "
        f"p95 changes are {pct(comparisons['qwen']['b4_p95_ttft_reduction_vs_b2'])} "
        f"and {pct(comparisons['mistral']['b4_p95_ttft_reduction_vs_b2'])}, respectively. "
        "B4 demonstrates compiler-layout portability only: it has no online PSTP "
        "or certificate issuance. SGLang prefix-token counters come directly from "
        "server logs and include Turn 0; vLLM counters cover future requests only. "
        "SGLang physical block IDs remain unavailable rather than inferred from timing.\n\n"
        + table
    )
    return text, "complete"


def llama_text(aggregate_path: Path, quality_path: Path, manifest_path: Path) -> str:
    row = read_csv(aggregate_path)[0]
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not quality.get("gate_pass") or int(row.get("scope_invalid_admitted_requests", 0)):
        raise ValueError("Llama qualified replay did not pass its frozen safety gate")
    families = ", ".join(manifest["qualified_task_families"])
    return (
        f"A development-only all-session gate prospectively qualifies `{families}` and rejects every other "
        f"Llama task family to raw order. Across {row['fresh_process_repeats']} fresh-process held-out repeats, "
        f"the qualified path reduces net mean TTFT by {pct(row['mean_net_mean_ttft_reduction'])}, p95 TTFT by "
        f"{pct(row['mean_p95_ttft_reduction'])}, and new-prefill work by "
        f"{pct(row['mean_new_prefill_reduction'])}. Fresh paired task scoring covers "
        f"{quality['paired_future_outputs']} future outputs with {quality['quality_violations']} quality "
        f"violations and {quality['scope_invalid_admitted']} scope-invalid admissions. This is empirical "
        "cross-model success inside a frozen task-family scope, not universal Llama support."
    )


def physical_text(path: Path) -> tuple[str, str]:
    rows = read_csv(path)
    if not rows:
        raise ValueError("physical dedup table is empty")
    lines = [
        "| Agents | Same-snapshot dedup blocks | Dedup KV GiB | Initial alloc raw/Contract | Peak used raw/Contract | Peak-used KV GiB saved | TTFT reduction | Refcount match | OOM-free lower bound |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['sessions']} | {f(row['net_concurrent_reference_blocks_avoided'])} | "
            f"{f(row['net_concurrent_kv_gib_saved'])} | "
            f"{f(row['raw_mean_newly_allocated_blocks'])}/{f(row['contract_mean_newly_allocated_blocks'])} | "
            f"{f(row['raw_mean_used_block_high_water'])}/{f(row['contract_mean_used_block_high_water'])} | "
            f"{f(row['peak_used_kv_gib_saved'])} | {pct(row['ttft_reduction'])} | "
            f"{pct(row['contract_peak_refcount_match_rate'])} | {row['oom_boundary']} |"
        )
    explanation = (
        "The primary dedup value is measured in one scheduler snapshot as logical shared references minus "
        "unique physical block IDs, net of the raw-order cell. Block-pool high-water supplies an independent "
        "peak check. Qwen's actual GQA geometry and float16 block size convert blocks to bytes. Cross-lifecycle "
        "block-ID reuse is diagnostic only, and new-prefill reduction is never used as a memory proxy."
    )
    return "\n".join(lines), explanation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aggregate", type=Path,
                        default=ROOT / "results/submission_repeats/submission_repeat_aggregate_v0.csv")
    parser.add_argument("--pairs", type=Path,
                        default=ROOT / "results/submission_repeats/submission_repeat_pairs_v0.csv")
    parser.add_argument("--external", type=Path,
                        default=ROOT / "results/external_baseline/external_prefix_baseline_summary_v0.json")
    parser.add_argument("--llama-aggregate", type=Path,
                        default=ROOT / "results/cross_model/llama_qualified_replay/aggregate_v0.csv")
    parser.add_argument("--llama-quality", type=Path,
                        default=ROOT / "results/cross_model/llama_qualified_replay/quality_summary_v0.json")
    parser.add_argument("--llama-manifest", type=Path,
                        default=ROOT / "results/cross_model/llama_qualified_replay/llama_task_qualification_v0.json")
    parser.add_argument("--physical", type=Path,
                        default=ROOT / "results/hard_systems/physical_dedup_memory_v0.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "submission")
    args = parser.parse_args()
    aggregate = read_csv(args.aggregate)
    pairs = read_csv(args.pairs)
    by_model = {row["model"]: row for row in aggregate}
    required = {"qwen", "mistral"}
    if set(by_model) != required:
        raise ValueError(f"expected exactly {required}, got {set(by_model)}")
    for model, row in by_model.items():
        if str(row.get("all_complete", "")).lower() != "true":
            raise ValueError(f"{model} repeat cell is incomplete")
        if int(row.get("scope_invalid_admitted_requests", 0)) != 0:
            raise ValueError(f"{model} admitted an invalid certificate scope")
    output = args.output; output.mkdir(parents=True, exist_ok=True)
    make_figure(aggregate, output / "figures/submission_main_metrics")
    external, external_status = external_text(args.external)
    llama = llama_text(args.llama_aggregate, args.llama_quality, args.llama_manifest)
    physical_table, physical_boundary = physical_text(args.physical)

    rows_md = []
    for model in ("qwen", "mistral"):
        row = by_model[model]
        rows_md.append(
            f"| {model.title()} | {pct(row['mean_net_mean_ttft_reduction'])} "
            f"[{pct(row['bootstrap95_low_net_mean_ttft_reduction'])}, "
            f"{pct(row['bootstrap95_high_net_mean_ttft_reduction'])}] | "
            f"{pct(row['mean_p95_ttft_reduction'])} | "
            f"{pct(row['mean_new_prefill_reduction'])} | "
            f"{pct(row['mean_slo_goodput_gain'])} | "
            f"{row['scope_invalid_admitted_requests']} |"
        )
    table = "\n".join([
        "| Model | Net mean TTFT reduction (bootstrap 95% CI) | p95 TTFT reduction | New-prefill reduction | SLO-goodput gain | Scope-invalid admitted |",
        "|---|---:|---:|---:|---:|---:|",
        *rows_md,
    ])

    manuscript = f"""# ContractKV: Verified Transactional Prefix Reuse for Agentic LLM Serving

## Abstract

Agent requests often contain a large stable context interrupted by changing tool observations. Linear prefix caches cannot reuse stable text beyond the first changed token, while unconstrained prompt reordering can silently change model behavior. ContractKV compiles dependency-valid agent prompts into cache-friendly layouts, verifies candidate behavior inside the serving engine, and transactionally publishes only a block-aligned stable prefix under an explicit certificate scope. On vLLM 0.10.2 with Qwen3-8B and Mistral-7B-Instruct-v0.3, three independent fresh-process repetitions at concurrency two show consistent reductions in prefill work and net TTFT after charging unhidden verification cost. A stale-scope Llama failure is repaired by prospective task-family qualification: the qualified held-out path succeeds while every unqualified family fails closed to raw order. ContractKV therefore treats certificate reuse as an empirical, scoped deployment policy rather than a universal semantic guarantee.

## 1. Introduction

Prefix caching is effective when requests repeat a byte- and token-identical prefix. Agent prompts violate this assumption: system instructions, repository context, and retrieved documents are stable, but tool observations and conversation state are inserted between them. The semantic working set is reusable even when its physical linear prefix is not.

Moving stable segments forward can expose this reuse, but creates two correctness hazards. First, segment order can encode dependencies, especially in code and chronological histories. Second, even dependency-valid layouts can change a model's output. Publishing an unverified candidate prefix makes that state visible to later requests. ContractKV addresses all three concerns jointly: a dependency-constrained cache-aware compiler proposes layouts, an in-engine verifier checks an empirical behavior contract, and prefix-selective transactional promotion publishes only the verified, full-block stable region.

This paper makes four contributions. It formulates agent prompt layout as dependency-valid prefix maximization over semantic segments; introduces scoped behavioral certificates that bind model, task, layout, stable content, policy, and observation or qualification state; implements fail-closed transactional prefix publication in the vLLM V1 path; and evaluates the complete path with task-bearing multi-turn traces, physical prefix metrics, fresh-process repetitions, and prospective cross-model qualification.

## 2. Motivation and Problem

Let a request consist of segments with semantic dependency edges. A raw layout preserves arrival order but may place volatile observations before long stable context. The native cache can then reuse only the longest common token prefix. A layout compiler may choose another topological order to increase the stable prefix, but must preserve all dependency edges and remain within a quality budget.

ContractKV optimizes expected prefill work subject to these constraints. The system does not claim arbitrary non-linear KV grafting: it compiles a legal linear prompt and uses the production prefix-cache substrate. The key systems problem is deciding which compiled prefixes may become visible and for how long their empirical attestations remain admissible.

## 3. Design

### 3.1 Dependency-constrained cache-aware compilation

The compiler represents segments as a DAG. Among legal topological orders it favors the order with the greatest overlap with resident stable prefixes, while retaining raw order when no qualified candidate is available. Stable system, schema, document, and repository segments can be grouped ahead of volatile observations only when dependencies permit it.

### 3.2 In-engine compact verification

A candidate is evaluated by the same backend using a frozen teacher-forced strict top-1 contract. The compact response carries the decision, transaction identity, committed-token count, and policy identity rather than a full token-by-token trace. Verification work is scheduled under a declared tool-slack budget; residual time is charged to net TTFT.

### 3.3 Prefix-selective transactional promotion

For block size B, stable-token boundary L_s, and computed boundary L_c, ContractKV publishes

```text
C = B * floor(min(L_s, L_c) / B).
```

Thus no partial block or dynamic suffix is promoted. A non-PASS report, duplicate transaction, timeout, or identity mismatch aborts with zero cache visibility change. Candidate state remains ephemeral until commit.

### 3.4 Scoped certificates

A certificate binds model identity, task family, layout hash, stable-prefix hash, scope mode, observation identity or epoch, policy hash, and qualification hash. Observation-scoped certificates expire when the observation changes. Qualified-session reuse is enabled only for a prospectively frozen model-task-layout qualification. Qualification is an empirical deployment policy, not a proof for arbitrary future inputs. Any mismatch fails closed to raw order.

## 4. Implementation

The prototype targets vLLM 0.10.2 and records physical prefix-hit and new-prefill tokens at the scheduler. The request runner creates identical fresh-process raw-order and ContractKV cells, alternates GPU assignment and launch order, and keeps each cell's process, port, cache state, and metrics log independent. Models and data remain on an 8 TB data volume. The final artifact excludes checkpoints, datasets, raw logs, and exploratory phases.

## 5. Evaluation

### 5.1 Setup

Experiments use one server with two RTX 3090 GPUs. The final repeat contains four cells: raw order and ContractKV for Qwen3-8B and Mistral-7B-Instruct-v0.3. Each cell is repeated three times from a fresh server process at concurrency two over the same sealed ten-turn traces. We report future turns only, include completion, p95, physical new-prefill work, and a 1,500 ms TTFT SLO, and add verification time not hidden by a 2,000 ms tool-slack window.

### 5.2 Fresh-process repeat results

{table}

All cells complete only if both policies finish every future request and no scope-invalid certificate is admitted. Figure 1 reports the paired reductions and deterministic 10,000-sample bootstrap intervals over the three independent process repetitions. The intervals quantify run-to-run system variation; three repetitions do not establish population-wide confidence.

![Fresh-process main results](figures/submission_main_metrics.png)

### 5.3 External prefix-cache substrate

{external}

### 5.4 Quality and cross-model boundary

The frozen Qwen evaluation certifies 34 of 50 sessions and reports zero unsafe certified sessions, zero dynamic-suffix reuse, and 99.98% stable-prefix physical reuse. The prospectively frozen Mistral split certifies 25 of 50 held-out sessions, completes 450/450 future requests, and reports zero future quality violations and 99.96% certified stable-prefix reuse. These are task-sanity and repository-standard scores, not full benchmark leaderboard claims.

The original Llama run exposed a causal boundary: three sessions became unsafe when an old Turn-0 certificate was reused for changed observations. Rechecking 11 reproducible rows caused fresh verification to reject or remain incomplete on ten; the remaining quality drop did not reproduce. No freshly accepted row remained quality-bad. The corrected prospective result is:

{llama}

### 5.5 Physical deduplication

{physical_table}

{physical_boundary}

## 6. Correctness Arguments

Transactional safety follows from publication gating: visibility changes only after PASS, policy identity match, and valid scope. Suffix isolation follows from the block-aligned commit equation. Scope safety is deliberately narrower: `Valid(c, x)` means the empirical attestation may be reused for request x; it does not imply universal semantic equivalence. Fault, duplicate, and mismatch paths abort without publication.

## 7. Related Systems

PagedAttention and vLLM provide the production KV-block and prefix-cache substrate. RadixAttention in SGLang demonstrates a stronger production prefix indexing substrate. ContractKV is orthogonal: it transforms semantically structured agent inputs into dependency-valid reusable prefixes, verifies the behavioral consequence, and controls publication. KV offload, quantization, and compression are compatible lifecycle primitives but are not part of the final main claim.

## 8. Limitations

Certificates are empirical and workload-qualified. Experiments use a single two-GPU RTX 3090 server and controlled agent traces rather than a production cluster trace. Llama success is restricted to the prospectively qualified task family; other families intentionally receive no layout optimization. Verifier coverage limits benefit, and the final artifact does not claim real host KV offload, KV quantization, arbitrary block grafting, or universal model safety.

## 9. Conclusion

ContractKV turns reusable semantic structure into safe physical prefix reuse by combining dependency-valid layout compilation, in-engine verification, scoped certificates, and transactional publication. Positive Qwen, Mistral, and prospectively qualified Llama results establish bounded cross-model transfer; the repaired Llama path shows why the validity boundary must be explicit. The final system claim is strong but disciplined: ContractKV reduces real serving work, physical duplication, and latency inside empirically qualified scopes and preserves raw-order behavior elsewhere.
"""
    (output / "contractkv_manuscript.md").write_text(manuscript, encoding="utf-8")

    appendix = f"""# ContractKV Submission Appendix

## A. Frozen fresh-process protocol

- Back end: vLLM 0.10.2, prefix caching enabled.
- Hardware: two RTX 3090 GPUs; each paired policy cell occupies one GPU.
- Load: concurrency 2, max model length 8,192, max sequences 2.
- Repetition: three fresh server processes per model-policy cell.
- Counterbalancing: GPU assignment alternates; repeat 2 reverses launch order.
- Workload: same sealed model-specific trace, ten turns, turn 0 unmeasured.
- Accounting: net TTFT adds verification time not hidden by 2,000 ms slack.
- SLO: 1,500 ms TTFT.

## B. Per-repeat paired data

| Model | Repeat | Raw mean TTFT | Contract net mean TTFT | Net reduction | p95 reduction | New-prefill reduction | SLO-goodput gain |
|---|---:|---:|---:|---:|---:|---:|---:|
"""
    for row in pairs:
        appendix += (f"| {row['model']} | {row['repeat']} | {f(row['raw_mean_ttft_ms'])} | "
                     f"{f(row['contract_net_mean_ttft_ms'])} | {pct(row['net_mean_ttft_reduction'])} | "
                     f"{pct(row['p95_ttft_reduction'])} | {pct(row['new_prefill_reduction'])} | "
                     f"{pct(row['slo_goodput_gain'])} |\n")
    appendix += f"""

## C. Certificate invalidation matrix

| Change | Observation scope | Qualified-session scope |
|---|---|---|
| Model identity | invalidate | invalidate |
| Task family | invalidate | invalidate |
| Dependency-valid layout | invalidate | invalidate |
| Stable-prefix content | invalidate | invalidate |
| Policy hash | invalidate | invalidate |
| Observation identity/epoch | invalidate | permitted only under frozen qualification |
| Qualification hash | not used | invalidate |

## D. External baseline boundary

{external}

External status: `{external_status}`. Official SGLang interfaces used by the
reproduction script are the OpenAI-compatible serving endpoint, streaming
latency path, metrics option, and `--disable-radix-cache` ablation. ContractKV
is not reimplemented inside SGLang.

## E. Reproduction entry points

```bash
bash scripts/run_submission_repeats.sh
bash scripts/install_sglang_external_baseline.sh
bash scripts/run_external_sglang_baseline.sh
bash scripts/run_llama_qualified_replay.sh
bash scripts/run_physical_dedup_submission.sh
python scripts/generate_submission_package.py
python scripts/build_paper_artifact.py
```

All models, Hugging Face caches, conda packages, logs, and raw request results
remain on the 8 TB data volume. Git tracks source, summarized evidence, and
hash manifests only.
"""
    (output / "contractkv_appendix.md").write_text(appendix, encoding="utf-8")

    claims = """# ContractKV Claim-Evidence Map

| Claim | Primary evidence | Boundary |
|---|---|---|
| ContractKV reduces real prefill work and net TTFT | `results/submission_repeats/submission_repeat_aggregate_v0.csv` | vLLM 0.10.2, c=2, frozen Qwen/Mistral traces, 2x3090 |
| Published state excludes the dynamic suffix | physical prefix metrics plus block-aligned PSTP commit | no arbitrary KV grafting or host offload claim |
| Unsafe evidence fails closed | scoped-certificate tests and mismatch counters | empirical attestation, not formal semantic proof |
| The mechanism transfers beyond Qwen | prospective Mistral and qualified Llama fresh-process heldout cells | bounded task-family scopes, not universal model coverage |
| Llama root cause is stale scope, not architecture | Phase 21A audit plus corrected qualified live replay | unqualified Llama families fail closed |
| Physical dedup saves KV blocks | 10/20-agent physical ID/refcount and block-pool high-water experiment | memory conversion uses actual model geometry, never prefill timing |
| Compiled layouts are portable across prefix substrates | SGLang B2/B4 RadixAttention A/B | B4 is offline layout consumption, no online PSTP/certificate |
"""
    (output / "claim_evidence_map.md").write_text(claims, encoding="utf-8")

    terminology = """# ContractKV Terminology Ledger

| Canonical term | Meaning | Avoid in main text |
|---|---|---|
| dependency-constrained cache-aware layout compiler | DAG-valid compiler guided by stable-prefix residency | CAPOSC, POSC unless historical context is essential |
| in-engine compact verification | same-backend empirical behavior check with compact egress | semantic proof |
| prefix-selective transactional promotion (PSTP) | publish only verified full-block stable prefix | arbitrary block grafting |
| scoped certificate | model/task/layout/content/policy-bound empirical attestation | reusable session certificate without qualification |
| observation scope | exact observation content and epoch | session-wide proof |
| qualified-session scope | prospectively frozen empirical deployment scope | universal future-input guarantee |
| new-prefill tokens | prompt tokens not physically served by prefix reuse | inferred cache hit rate |
| net mean TTFT | observed mean TTFT plus unhidden verifier cost | free verification |
| raw-order | original dependency-safe prompt order with native prefix cache | no-cache baseline |
"""
    (output / "terminology_ledger.md").write_text(terminology, encoding="utf-8")

    closeout = f"""# ContractKV Submission Hardening Closeout

## Decision

The research phase is frozen. Submission hardening is complete: certificate
scope is explicit in code and documentation, Qwen and Mistral core cells have
three fresh-process repetitions, the external prefix-cache baseline status is
recorded, and a minimal hash-audited artifact plus paper package is generated.

## Main repeated result

{table}

## External baseline

{external}

## Qualified Llama replay

{llama}

## Physical deduplication

{physical_table}

{physical_boundary}

## Claim discipline

The paper claims real vLLM prefix-work, TTFT, and SLO behavior only in the
measured qualified scopes. It does not claim universal certificates, real KV
offload or quantization, production-cluster throughput, or full benchmark
leaderboard accuracy.

## Actual result-producing code in this hardening round

- `scripts/contractkv_certificate_scope.py`
- `scripts/contractkv_transaction.py`
- `scripts/phase17_live_common.py`
- `scripts/install_vllm_v1_phase17_hook.py`
- `scripts/phase19b_end_to_end_live.py`
- `scripts/run_submission_repeats.sh`
- `scripts/summarize_submission_repeats.py`
- `scripts/install_sglang_external_baseline.sh`
- `scripts/run_external_sglang_raw_replay.py`
- `scripts/run_external_sglang_baseline.sh`
- `scripts/summarize_external_system_matrix.py`
- `scripts/run_remaining_submission_experiments.sh`
- `scripts/freeze_llama_task_qualification.py`
- `scripts/run_llama_qualified_replay.sh`
- `scripts/score_llama_qualified_replay.py`
- `scripts/phase14m_physical_dedup.py`
- `scripts/run_physical_dedup_submission.sh`
- `scripts/summarize_physical_dedup_memory.py`
- `scripts/repair_submission_scope_telemetry.py`
- `scripts/generate_submission_package.py`
- `scripts/build_paper_artifact.py`

Historical modules imported by the final request path are enumerated in the
artifact manifest. Test files are intentionally not listed here.
"""
    (ROOT / "docs/submission_hardening_closeout.md").write_text(closeout, encoding="utf-8")
    repeat_report = f"""# Submission Fresh-Process Repeat Report

## Protocol

Qwen3-8B and Mistral-7B-Instruct-v0.3 each run raw-order and ContractKV at
concurrency two. Every model-policy cell has three independent vLLM server
processes. GPU assignment alternates, repeat 2 reverses launch order, turn 0 is
unmeasured, and all summaries use identical future-turn keys. Net mean TTFT
charges verification time outside the frozen 2,000 ms tool-slack window.

## Results

{table}

The bootstrap interval is a deterministic 10,000-resample interval over three
paired process repeats. The report also retains the full cross-run range in
`submission_repeat_aggregate_v0.csv`. Scope-invalid certificates may only
appear as raw-order fallbacks; the `scope_invalid_admitted_requests` count must
remain zero.
"""
    (ROOT / "docs/submission_fresh_process_repeat_report.md").write_text(
        repeat_report, encoding="utf-8")
    external_report = f"""# External SGLang Prefix-Cache Baseline

## Purpose

This A-tier baseline asks whether a production RadixAttention substrate alone
recovers reuse from the unchanged raw-order agent trace. It does not port
ContractKV to SGLang.

## Frozen setup

- Same Qwen3-8B and Mistral-7B checkpoints and model-specific sealed traces as the main repeat.
- Concurrency 2, ten turns, turn 0 warm-up, 8,192-token context.
- B1: vLLM APC with raw order (reused from the main repeat).
- B2: SGLang RadixAttention with raw order.
- B3: vLLM APC with online verified compiled order (reused from the main repeat).
- B4: SGLang RadixAttention with offline frozen safe compiled order.
- Isolated conda-first environment and caches on the 8 TB data volume.
- SGLang uses its Triton attention backend and PyTorch sampler because the host CUDA 11.2 toolkit cannot JIT the cu12 FlashInfer wheel; RadixAttention remains enabled in every SGLang cell.

## Result

{external}

## Evidence boundary

The runner reports streaming TTFT, TPOT, completion, prompt tokens, and SLO
goodput. Cached/new-prefill counts are read from SGLang's real server log and
their all-request scope (including Turn 0) is explicit; no cache hit is
reconstructed from timing. Physical block IDs remain unavailable. The launch and ablation interfaces
follow the official SGLang serving and observability documentation:

- https://docs.sglang.ai/developer_guide/bench_serving
- https://docs.sglang.ai/advanced_features/observability.html
"""
    (ROOT / "docs/external_sglang_prefix_baseline_report.md").write_text(
        external_report, encoding="utf-8")
    (ROOT / "docs/llama_qualified_cross_model_report.md").write_text(
        "# Llama Qualified Cross-Model Replay\n\n" + llama + "\n", encoding="utf-8")
    (ROOT / "docs/physical_dedup_memory_report.md").write_text(
        "# Physical Prefix Deduplication\n\n" + physical_table + "\n\n" + physical_boundary + "\n",
        encoding="utf-8")
    diagnostics = """# Submission Experiment Diagnostics

## Method-level finding

The original Llama failure was a certificate-contract error: a Turn-0
attestation was reused after the observation state changed. Fresh re-attestation
rejected ten of eleven reproducible bad rows, and the remaining drop did not
reproduce. The corrected design freezes qualification from development only and
fails closed outside the qualified model-task-layout scope.

## Engineering faults found and excluded

- An asynchronous result row inherited another future's `scope_errors`. The
  repair changes telemetry only and records before/after hashes; executed policy,
  timing, prefix metrics, and outputs are unchanged.
- The first SGLang launch expanded a `local` shell variable before assignment.
- Absolute Python invocation omitted the conda environment's `ninja` from PATH.
- The host CUDA toolkit is 11.2 although the isolated Torch wheel is cu126;
  FlashInfer JIT therefore lacked a compatible `cuda_fp8.h`. Every valid SGLang
  cell uses the same Triton attention and PyTorch sampling backend with
  RadixAttention enabled.
- A stale watcher launched a duplicate external replay, and forced parent-only
  termination left an orphan scheduler. All partial files were discarded. The
  final runner holds a single-driver `flock` and terminates an isolated process
  group per fresh server cell.
- Updating the shell runner while its first process was still reading the file
  corrupted that process's tail parse after Qwen completed. A strict resumable
  cell gate now skips only 500-row, 450-future-request, fully completed cells;
  the repaired runner resumed at Mistral without overwriting Qwen evidence.
- The isolated SGLang environment initially lacked `protobuf`, which the
  Mistral tokenizer requires. The dependency is pinned in the conda-first
  installer; no model or result code changed.
- The per-cell `mean_newly_allocated_blocks` diagnostic used a request-lifetime
  maximum that included decode growth. The final memory table reconstructs
  initial prompt allocation from effective unique minus reused blocks, and the
  reproduction code now reads the initial scheduler event directly. Physical
  IDs, same-snapshot refcounts, block-pool high-water, TTFT, and outputs were
  unaffected.

These are environment, orchestration, or telemetry bugs. None of their partial
outputs enters a summarized result or paper artifact.
"""
    (ROOT / "docs/submission_experiment_diagnostics.md").write_text(
        diagnostics, encoding="utf-8")
    manifest = f"""batch: submission_hardening_v1
status: complete
research_scope: frozen
models:
  - Qwen3-8B
  - Mistral-7B-Instruct-v0.3
negative_boundary_model: Llama-3.1-8B-Instruct
backend: vllm-0.10.2
hardware: 2x-RTX-3090
fresh_process_repeats: 3
concurrency: 2
turns: 10
ttft_slo_ms: 1500
tool_slack_ms: 2000
certificate_scope_modes:
  - observation
  - qualified_session
external_baseline_status: {external_status}
results:
  - results/submission_repeats/submission_repeat_cells_v0.csv
  - results/submission_repeats/submission_repeat_pairs_v0.csv
  - results/submission_repeats/submission_repeat_aggregate_v0.csv
  - results/submission_repeats/submission_repeat_summary_v0.json
  - results/external_baseline/external_prefix_baseline_summary_v0.json
  - results/cross_model/llama_qualified_replay/aggregate_v0.csv
  - results/cross_model/llama_qualified_replay/quality_summary_v0.json
  - results/hard_systems/physical_dedup_memory_v0.csv
paper:
  - submission/contractkv_manuscript.md
  - submission/contractkv_appendix.md
  - submission/claim_evidence_map.md
  - submission/terminology_ledger.md
claim_boundary: scoped empirical certificates and real prefix reuse; no universal semantic proof or real KV offload claim
"""
    (ROOT / "results/manifests/submission_hardening_v1.yaml").write_text(
        manifest, encoding="utf-8")
    print(json.dumps({"output": str(output), "external_status": external_status,
                      "models": sorted(by_model)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
