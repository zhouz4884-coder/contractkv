#!/usr/bin/env python3
"""Apply repository-standard metrics to frozen Phase 19 outputs only."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import statistics
import string
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


PAIR_FIELDS = [
    "phase", "partition", "load_tier", "dataset", "task", "sample_id",
    "pair_id", "policy", "certified", "frozen_unsafe", "raw_score",
    "policy_score", "paired_difference", "scorable", "score_error",
    "metric", "metric_source",
]
SUMMARY_FIELDS = [
    "phase", "partition", "load_tier", "dataset", "task", "policy",
    "pairs", "raw_mean", "policy_mean", "paired_difference",
    "bootstrap_ci_low", "bootstrap_ci_high", "material_drop_gt_0_03",
    "certified", "unsafe_certified", "metric", "metric_source",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def truth(value: object) -> bool:
    return value is True or str(value).lower() == "true"


def normalize_answer(value: str) -> str:
    def remove_articles(text: str) -> str:
        return re.sub(r"\b(a|an|the)\b", " ", text)
    exclude = set(string.punctuation)
    value = "".join(ch for ch in value.lower() if ch not in exclude)
    return " ".join(remove_articles(value).split())


def qa_f1(prediction: str, answer: str) -> float:
    prediction_tokens = normalize_answer(prediction).split()
    answer_tokens = normalize_answer(answer).split()
    if not prediction_tokens or not answer_tokens:
        return float(prediction_tokens == answer_tokens)
    common = Counter(prediction_tokens) & Counter(answer_tokens)
    same = sum(common.values())
    if not same:
        return 0.0
    precision = same / len(prediction_tokens)
    recall = same / len(answer_tokens)
    return 2 * precision * recall / (precision + recall)


def references(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def standard_score(dataset: str, task: str, prediction: str,
                   answer: object) -> tuple[float, str, str]:
    refs = references(answer)
    if dataset == "RULER":
        score = max(float(ref.lower() in prediction.lower()) for ref in refs)
        return score, "string_match_part", "RULER scripts/eval/synthetic/constants.py"
    if dataset == "LongBench" and task in {"hotpotqa", "qasper", "narrativeqa"}:
        score = max(qa_f1(prediction, ref) for ref in refs)
        return score, "qa_f1", "LongBench/metrics.py:qa_f1_score"
    if dataset == "RepoBench":
        ref = refs[0]
        # RepoBench reports both EM and edit similarity. Edit similarity is the
        # continuous primary metric used here; exact equality remains in the
        # pair file through a 1.0 score.
        score = round(100 * SequenceMatcher(None, prediction, ref).ratio()) / 100
        return score, "edit_similarity", "repobench/evaluation/metrics.py:edit_similarity_score (formula-equivalent)"
    raise ValueError(f"unsupported standard metric: {dataset}/{task}")


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * q
    lower = int(index); upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def bootstrap_ci(rows: list[dict[str, Any]], repeats: int, seed: int) -> tuple[float, float]:
    groups: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        groups[str(row["sample_id"])].append(float(row["paired_difference"]))
    keys = sorted(groups)
    if not keys:
        return 0.0, 0.0
    rng = random.Random(seed)
    draws = []
    for _ in range(repeats):
        sampled = [rng.choice(keys) for _ in keys]
        values = [value for key in sampled for value in groups[key]]
        draws.append(statistics.mean(values))
    return percentile(draws, .025), percentile(draws, .975)


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase19a-quality", type=Path, required=True)
    parser.add_argument("--raw-cache", type=Path, required=True)
    parser.add_argument("--candidate-cache", type=Path, required=True)
    parser.add_argument("--full-pool", type=Path, required=True)
    parser.add_argument("--phase19b-raw", type=Path, required=True)
    parser.add_argument("--phase19b-sessions", type=Path, required=True)
    parser.add_argument("--bootstrap-repeats", type=int, default=2000)
    parser.add_argument("--pairs-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--gate-output", type=Path, required=True)
    args = parser.parse_args()

    pool = {f"{row['dataset']}::{row['task']}::{row['sample_id']}": row
            for row in load_jsonl(args.full_pool)}
    raw_cache = {str(row.get("request_id")): row for row in load_jsonl(args.raw_cache)}
    candidate_cache = {str(row.get("request_id")): row for row in load_jsonl(args.candidate_cache)}
    pairs: list[dict[str, Any]] = []
    with args.phase19a_quality.open(encoding="utf-8", newline="") as handle:
        quality_rows = list(csv.DictReader(handle))
    for row in quality_rows:
        sample = pool[str(row["sample_key"])]
        raw_record = raw_cache.get(str(row["raw_request_id"]))
        candidate_record = candidate_cache.get(str(row["candidate_request_id"]))
        scorable = bool(raw_record and candidate_record and
                        raw_record.get("protocol_status") == "COMPLETE" and
                        candidate_record.get("protocol_status") == "COMPLETE")
        metric = "unavailable"; source = "frozen output incomplete"
        raw_score: float | str = ""; candidate_score: float | str = ""
        if scorable:
            raw_text = str(raw_record.get("output_text", ""))
            candidate_text = str(candidate_record.get("output_text", ""))
            raw_score, metric, source = standard_score(row["dataset"], row["task"], raw_text, sample.get("answer", ""))
            candidate_score, _, _ = standard_score(row["dataset"], row["task"], candidate_text, sample.get("answer", ""))
        certified = truth(row["certificate_eligible"])
        for policy, score in (("candidate-layout", candidate_score),
                              ("contractkv-effective", candidate_score if certified else raw_score)):
            pairs.append({
                "phase": "phase19a", "partition": row["partition"], "load_tier": "",
                "dataset": row["dataset"], "task": row["task"], "sample_id": row["sample_id"],
                "pair_id": row["candidate_id"], "policy": policy, "certified": certified,
                "frozen_unsafe": truth(row["fresh_unsafe_label"]), "raw_score": raw_score,
                "policy_score": score,
                "paired_difference": float(score) - float(raw_score) if scorable else "",
                "scorable": scorable,
                "score_error": "" if scorable else "frozen_generation_incomplete",
                "metric": metric, "metric_source": source,
            })

    sessions = {str(row["phase19b_session_id"]): row for row in load_jsonl(args.phase19b_sessions)}
    live = load_jsonl(args.phase19b_raw)
    raw_index = {(row["load_tier"], row["session_id"], int(row["turn_id"])): row
                 for row in live if row.get("row_type") == "future" and row.get("policy") == "raw-order"}
    for row in live:
        if row.get("row_type") != "future" or row.get("policy") not in {"physical-cache-aware", "contractkv-full"}:
            continue
        key = (row["load_tier"], row["session_id"], int(row["turn_id"]))
        raw = raw_index[key]; sample = sessions[str(row["session_id"])]
        raw_score, metric, source = standard_score(str(row["dataset"]), str(row["task"]),
                                                   str(raw.get("output_text", "")), sample.get("answer", ""))
        policy_score, _, _ = standard_score(str(row["dataset"]), str(row["task"]),
                                            str(row.get("output_text", "")), sample.get("answer", ""))
        pairs.append({
            "phase": "phase19b", "partition": "untouched", "load_tier": row["load_tier"],
            "dataset": row["dataset"], "task": row["task"], "sample_id": row["sample_id"],
            "pair_id": f"{row['session_id']}:{row['turn_id']}", "policy": row["policy"],
            "certified": truth(row.get("certificate_issued")), "frozen_unsafe": "",
            "raw_score": raw_score, "policy_score": policy_score,
            "paired_difference": policy_score - raw_score, "metric": metric,
            "metric_source": source, "scorable": True, "score_error": "",
        })

    args.pairs_output.parent.mkdir(parents=True, exist_ok=True)
    with args.pairs_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PAIR_FIELDS); writer.writeheader(); writer.writerows(pairs)

    groups: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in pairs:
        if not truth(row.get("scorable")):
            continue
        key = tuple(str(row[field]) for field in ("phase", "partition", "load_tier", "dataset", "task", "policy"))
        groups[key].append(row)
    summaries = []
    for index, (key, rows) in enumerate(sorted(groups.items())):
        low, high = bootstrap_ci(rows, args.bootstrap_repeats, 20260713 + index)
        difference = statistics.mean(float(row["paired_difference"]) for row in rows)
        summaries.append({
            **dict(zip(("phase", "partition", "load_tier", "dataset", "task", "policy"), key)),
            "pairs": len(rows), "raw_mean": statistics.mean(float(row["raw_score"]) for row in rows),
            "policy_mean": statistics.mean(float(row["policy_score"]) for row in rows),
            "paired_difference": difference, "bootstrap_ci_low": low, "bootstrap_ci_high": high,
            "material_drop_gt_0_03": difference < -.03,
            "certified": sum(truth(row["certified"]) for row in rows),
            "unsafe_certified": sum(truth(row["certified"]) and truth(row["frozen_unsafe"]) for row in rows),
            "metric": rows[0]["metric"], "metric_source": rows[0]["metric_source"],
        })
    with args.summary_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS); writer.writeheader(); writer.writerows(summaries)

    deployed = [row for row in summaries if row["policy"] in {"contractkv-effective", "contractkv-full"}]
    gate = {
        "phase19a_pairs": sum(row["phase"] == "phase19a" and row["policy"] == "candidate-layout" for row in pairs),
        "phase19a_scorable_pairs": sum(row["phase"] == "phase19a" and row["policy"] == "candidate-layout" and truth(row["scorable"]) for row in pairs),
        "phase19b_contractkv_pairs": sum(row["phase"] == "phase19b" and row["policy"] == "contractkv-full" for row in pairs),
        "candidate_identity_unchanged": len({row["candidate_id"] for row in quality_rows}) == len(quality_rows),
        "policy_hash_unchanged": len({row["policy_hash"] for row in quality_rows}) == 1,
        "official_material_drop_absent": all(not truth(row["material_drop_gt_0_03"]) for row in deployed),
        "unsafe_certified_zero": all(int(row["unsafe_certified"]) == 0 for row in deployed),
        "inputs": {path.name: file_hash(path) for path in (
            args.phase19a_quality, args.raw_cache, args.candidate_cache,
            args.phase19b_raw, args.phase19b_sessions)},
        "claim_boundary": "Repository-standard offline scoring of frozen outputs; references never enter online admission.",
    }
    gate["gate_pass"] = all(value for key, value in gate.items()
                            if key not in {"phase19a_pairs", "phase19b_contractkv_pairs", "inputs", "claim_boundary", "gate_pass"})
    args.gate_output.write_text(json.dumps(gate, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(gate, indent=2)); return 0 if gate["gate_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
