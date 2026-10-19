"""Reanalyse archived serving evidence without changing original results."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import statistics
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.summarize_submission_supplement import percentile
from scripts.phase20a_official_quality import standard_score


def read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def request_class(row: dict) -> str:
    if row.get("certificate_issued") is True:
        return "admitted_compiled"
    if row.get("requested_level") == "L0" or row.get("verify_decision") == "NOT_REQUIRED":
        return "manifest_direct_raw"
    return "runtime_raw_fallback"


def cost_table(raw: list[dict], candidate: list[dict], model: str, repeat: int,
               slack_ms: float) -> list[dict]:
    reference = {(str(row.get("session_id")), int(row.get("turn_id", -1))): row
                 for row in raw if row.get("row_type") == "future"}
    future = [row for row in candidate if row.get("row_type") == "future"]
    canaries = [row for row in candidate if row.get("row_type") == "canary"]
    session_cost: dict[str, float] = defaultdict(float)
    full_cost_available: dict[str, bool] = defaultdict(lambda: True)
    for row in canaries:
        # latency_ms includes raw-reference generation, tokenize and endpoint.
        # Keep endpoint-only and full registration costs separately.
        session_cost[str(row.get("session_id"))] += float(
            row.get("latency_ms", row.get("verification_ms", 0)) or 0)
        if "latency_ms" not in row:
            full_cost_available[str(row.get("session_id"))] = False
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in future:
        grouped[request_class(row)].append(row)
        grouped["ALL"].append(row)
    results = []
    for cls, rows in grouped.items():
        ids = {str(row.get("session_id")) for row in rows}
        full_cost = sum(session_cost.get(sid, 0) for sid in ids)
        complete_timing = all(full_cost_available[sid] for sid in ids)
        residual = sum(max(session_cost.get(sid, 0) - slack_ms, 0) for sid in ids)
        successes = [row for row in rows if row.get("success") is True]
        paired = [(row, reference.get((str(row.get("session_id")), int(row.get("turn_id", -1)))))
                  for row in successes]
        paired = [(row, ref) for row, ref in paired if ref and ref.get("success") is True]
        raw_ttft = [float(ref["ttft_ms"]) for _, ref in paired]
        measured = [float(row["ttft_ms"]) for row, _ in paired]
        raw_mean = statistics.fmean(raw_ttft) if raw_ttft else 0
        observed = statistics.fmean(measured) if measured else 0
        exposure = residual / max(len(rows), 1)
        results.append({
            "model": model, "repeat": repeat, "request_class": cls,
            "slack_ms": slack_ms, "requests": len(rows), "completed_requests": len(successes),
            "completion_rate": len(successes) / max(len(rows), 1), "paired_successes": len(paired),
            "full_registration_timing_available": complete_timing,
            "recorded_registration_ms": full_cost, "recorded_unhidden_registration_ms": residual,
            "full_registration_ms_per_future": full_cost / max(len(rows), 1) if complete_timing else "unavailable",
            "unhidden_registration_ms_per_future": exposure,
            "raw_mean_ttft_ms": raw_mean, "observed_mean_ttft_ms": observed,
            "full_cost_net_mean_ttft_ms": observed + full_cost / max(len(rows), 1) if complete_timing else "unavailable",
            "net_mean_ttft_ms": observed + exposure,
            "net_mean_ttft_reduction": 1 - (observed + exposure) / raw_mean if raw_mean else "",
            "observed_p95_ttft_ms": percentile(measured, .95),
            "observed_p99_ttft_ms": percentile(measured, .99),
            "endpoint_only_ms": sum(float(row.get("verification_ms", 0) or 0)
                                    for row in canaries if str(row.get("session_id")) in ids),
            "cost_source": ("archived canary latency_ms; all future denominator" if complete_timing else
                            "endpoint timing only; lower bound; raw-reference and rejected-attempt costs not fully archived"),
            "claim_boundary": "Historical measured costs reaccounted offline; missing full timings are explicit; not fresh live goodput or actual p99 overlap."
        })
    return results


def archived_divergence(raw: list[dict], candidate: list[dict], model: str,
                        repeat: int, samples: dict[str, dict]) -> list[dict]:
    reference = {(str(row.get("session_id")), int(row.get("turn_id", -1))): row
                 for row in raw if row.get("row_type") == "future"}
    results = []
    for row in candidate:
        if row.get("row_type") != "future":
            continue
        sid, turn = str(row.get("session_id")), int(row.get("turn_id", -1))
        ref = reference.get((sid, turn))
        if ref is None:
            raise ValueError(f"Missing archived paired request: {model}/{repeat}/{sid}/{turn}")
        sample = samples.get(sid)
        text_raw, text_candidate = str(ref.get("output_text", "")), str(row.get("output_text", ""))
        score_raw = score_candidate = ""
        if sample and row.get("success") is True and ref.get("success") is True:
            score_raw = standard_score(str(sample["dataset"]), str(sample["task"]),
                                       text_raw, sample.get("answer", ""))[0]
            score_candidate = standard_score(str(sample["dataset"]), str(sample["task"]),
                                             text_candidate, sample.get("answer", ""))[0]
        token_raw, token_candidate = ref.get("output_token_ids"), row.get("output_token_ids")
        results.append({
            "model": model, "repeat": repeat, "session_id": sid, "turn_id": turn,
            "dataset": row.get("dataset", ""), "task": row.get("task", ""),
            "request_class": request_class(row), "both_success": bool(row.get("success") and ref.get("success")),
            "text_identical": text_raw == text_candidate,
            "token_ids_available": isinstance(token_raw, list) and isinstance(token_candidate, list),
            "token_identical": token_raw == token_candidate if isinstance(token_raw, list) and isinstance(token_candidate, list) else "unavailable",
            "raw_score": score_raw, "candidate_score": score_candidate,
            "quality_drop": score_raw - score_candidate if score_raw != "" else "",
            "raw_finish_reason": ref.get("finish_reason", "unavailable"),
            "candidate_finish_reason": row.get("finish_reason", "unavailable"),
            "claim_boundary": "Archived free text outputs; original prompts and budgets unchanged; token IDs may be unavailable."
        })
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    specs = [
        ("Qwen3-8B", "results/submission_repeats/qwen", "repeat{r}/raw-order.jsonl", "repeat{r}/contractkv-full.jsonl", "results/end_to_end/phase19b_untouched_sessions_v0.jsonl"),
        ("Mistral-7B-Instruct-v0.3", "results/submission_repeats/mistral", "repeat{r}/raw-order.jsonl", "repeat{r}/contractkv-full.jsonl", "results/mistral/heldout_sealed_sessions_v0.jsonl"),
        ("Llama-3.1-8B-Instruct", "results/cross_model/llama_broad_generalization_r3", "repeat{r}/r{r}-raw.jsonl", "repeat{r}/r{r}-contract.jsonl", "results/cross_model/llama_broad_generalization_r3/heldout_sealed_sessions_v0.jsonl"),
        ("Qwen3-14B-TP2", "results/scale_up/qwen3_14b_tp2_v0", "r{r}/r{r}-raw.jsonl", "r{r}/r{r}-contract.jsonl", "results/scale_up/qwen3_14b_tp2_v0/frozen_sessions_v0.jsonl"),
    ]
    costs, outputs, sources = [], [], []
    for model, root, raw_pattern, candidate_pattern, sample_path in specs:
        samples = {str(row.get("phase19b_session_id")): row for row in read_rows(args.root / sample_path)}
        for repeat in (1, 2, 3):
            raw_path = args.root / root / raw_pattern.format(r=repeat)
            candidate_path = args.root / root / candidate_pattern.format(r=repeat)
            raw, candidate = read_rows(raw_path), read_rows(candidate_path)
            sources.extend({"path": str(path.relative_to(args.root)), "sha256": sha(path)}
                           for path in (raw_path, candidate_path))
            for slack in (0, 500, 2000, 6000):
                costs.extend(cost_table(raw, candidate, model, repeat, slack))
            outputs.extend(archived_divergence(raw, candidate, model, repeat, samples))
    args.output.mkdir(parents=True, exist_ok=True)
    write_csv(args.output / "historical_full_cost_by_repeat_v1.csv", costs)
    write_csv(args.output / "historical_free_text_pairs_v1.csv", outputs)
    summary = []
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in outputs:
        groups[(row["model"], row["request_class"])].append(row)
        groups[(row["model"], "ALL")].append(row)
    for (model, cls), rows in sorted(groups.items()):
        scorable = [row for row in rows if row["quality_drop"] != ""]
        summary.append({"model": model, "request_class": cls, "requests": len(rows),
                        "both_successes": sum(row["both_success"] for row in rows),
                        "text_divergences": sum(not row["text_identical"] for row in rows),
                        "text_divergence_rate": sum(not row["text_identical"] for row in rows) / len(rows),
                        "scorable": len(scorable),
                        "material_score_drops_gt_0_03": sum(row["quality_drop"] > .03 for row in scorable),
                        "mean_quality_drop": statistics.fmean(row["quality_drop"] for row in scorable) if scorable else "",
                        "claim_boundary": "Archived finite-budget generations; not the new long-output experiment."})
    write_csv(args.output / "historical_free_text_summary_v1.csv", summary)
    manifest = {"schema_version": "tsc-revision-historical-audit.v1", "status": "complete",
                "source_files": sources, "models": [spec[0] for spec in specs],
                "cost_rows": len(costs), "output_pairs": len(outputs)}
    (args.output / "historical_audit_manifest_v1.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in manifest.items() if key != "source_files"}))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
