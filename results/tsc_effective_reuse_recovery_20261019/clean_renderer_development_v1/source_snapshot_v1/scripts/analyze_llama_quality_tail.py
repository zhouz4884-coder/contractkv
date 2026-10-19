#!/usr/bin/env python3
"""Close the Llama quality-regression and tail-mixture audit from raw logs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase20a_official_quality import standard_score


CASE_SESSION = "phase22r-narrativeqa-158"
CASE_TURN = 2


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1))
    return ordered[index]


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def key(row: dict[str, Any]) -> tuple[str, int]:
    return str(row.get("session_id", "")), int(row.get("turn_id", -1))


def score(row: dict[str, Any], sessions: dict[str, dict[str, Any]]) -> float:
    sample = sessions[str(row["session_id"])]
    value, _, _ = standard_score(
        str(sample.get("dataset", row.get("dataset", ""))),
        str(sample.get("task", row.get("task", ""))),
        str(row.get("output_text", "")),
        sample.get("answer", ""),
    )
    return float(value)


def contract_class(row: dict[str, Any]) -> str:
    effective = str(row.get("effective_level", "L0"))
    requested = str(row.get("requested_level", "L0"))
    admitted = (effective != "L0" and bool(row.get("certificate_issued"))
                and bool(row.get("certificate_scope_valid", True)))
    if admitted:
        return "admitted_compiled"
    if requested == "L0":
        return "manifest_direct_l0"
    return "runtime_fallback"


def first_divergence(left: list[int], right: list[int]) -> int | None:
    for index, (a, b) in enumerate(zip(left, right)):
        if a != b:
            return index
    return min(len(left), len(right)) if len(left) != len(right) else None


def text_divergence(left: str, right: str) -> int | None:
    for index, (a, b) in enumerate(zip(left, right)):
        if a != b:
            return index
    return min(len(left), len(right)) if len(left) != len(right) else None


def repeat_paths(root: Path) -> list[tuple[Path, Path]]:
    broad = root / "results/cross_model/llama_broad_generalization_r3"
    direct = root / "results/external_baseline/llama_direct_v1"
    return [
        *((broad / f"repeat{i}" / f"r{i}-raw.jsonl",
           broad / f"repeat{i}" / f"r{i}-contract.jsonl") for i in range(1, 4)),
        *((direct / f"llama-r{i}-raw.jsonl",
           direct / f"llama-r{i}-contract.jsonl") for i in range(4, 6)),
    ]


def summarize_group(
    label: str,
    rows: list[dict[str, Any]],
    raw_maps: list[dict[tuple[str, int], dict[str, Any]]],
) -> dict[str, Any]:
    ttft = [float(row["ttft_ms"]) for row in rows if row.get("success") is True]
    raw_ttft = [float(raw_maps[int(row["_repeat"]) - 1][key(row)]["ttft_ms"])
                for row in rows if key(row) in raw_maps[int(row["_repeat"]) - 1]]
    prompt = [float(row["prompt_tokens"]) for row in rows if row.get("prompt_tokens") not in (None, "")]
    hits = [float(row["prefix_hit_tokens"]) for row in rows if row.get("prefix_hit_tokens") not in (None, "")]
    new_prefill = [float(row["new_prefill_tokens"]) for row in rows if row.get("new_prefill_tokens") not in (None, "")]
    mean = statistics.fmean(ttft) if ttft else 0.0
    raw_mean = statistics.fmean(raw_ttft) if raw_ttft else 0.0
    return {
        "request_class": label,
        "requests": len(rows),
        "share": len(rows) / 2250.0,
        "completion_rate": len(ttft) / max(1, len(rows)),
        "mean_ttft_ms": mean,
        "p50_ttft_ms": percentile(ttft, 0.50),
        "p95_ttft_ms": percentile(ttft, 0.95),
        "p99_ttft_ms": percentile(ttft, 0.99),
        "paired_raw_mean_ttft_ms": raw_mean,
        "mean_ttft_reduction_vs_paired_raw": ((raw_mean - mean) / raw_mean
                                                if raw_mean else 0.0),
        "slo_1500_attainment": sum(value <= 1500.0 for value in ttft) / max(1, len(ttft)),
        "mean_prompt_tokens": statistics.fmean(prompt) if prompt else None,
        "mean_prefix_hit_tokens": statistics.fmean(hits) if hits else None,
        "mean_new_prefill_tokens": statistics.fmean(new_prefill) if new_prefill else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--tokenizer-path", type=Path)
    parser.add_argument("--quality-output", type=Path, required=True)
    parser.add_argument("--tail-json", type=Path, required=True)
    parser.add_argument("--tail-csv", type=Path, required=True)
    args = parser.parse_args()

    sessions = {str(row["phase19b_session_id"]): row for row in load_jsonl(args.sessions)}
    raw_repeats: list[list[dict[str, Any]]] = []
    contract_repeats: list[list[dict[str, Any]]] = []
    canaries: list[dict[str, Any]] = []
    for repeat, (raw_path, contract_path) in enumerate(repeat_paths(args.root), start=1):
        raw_all = load_jsonl(raw_path)
        contract_all = load_jsonl(contract_path)
        raw_rows = [row for row in raw_all if row.get("row_type") == "future"]
        contract_rows = [row for row in contract_all if row.get("row_type") == "future"]
        for row in raw_rows + contract_rows:
            row["_repeat"] = repeat
            row["_score"] = score(row, sessions)
        raw_repeats.append(raw_rows)
        contract_repeats.append(contract_rows)
        canary = next(row for row in contract_all
                      if row.get("row_type") == "canary"
                      and row.get("session_id") == CASE_SESSION)
        canaries.append(canary)

    raw_maps = [{key(row): row for row in rows} for rows in raw_repeats]
    contract_maps = [{key(row): row for row in rows} for rows in contract_repeats]
    paired: list[dict[str, Any]] = []
    for repeat in range(5):
        for request_key, candidate in contract_maps[repeat].items():
            baseline = raw_maps[repeat][request_key]
            delta = candidate["_score"] - baseline["_score"]
            paired.append({
                "repeat": repeat + 1,
                "session_id": request_key[0],
                "turn_id": request_key[1],
                "request_class": contract_class(candidate),
                "raw_score": baseline["_score"],
                "contract_score": candidate["_score"],
                "score_delta": delta,
                "material_regression": delta < -0.03,
            })

    raw_controls: list[dict[str, Any]] = []
    for repeat in range(5):
        left = raw_maps[repeat]
        right = raw_maps[(repeat + 1) % 5]
        for request_key, baseline in left.items():
            candidate = right[request_key]
            delta = candidate["_score"] - baseline["_score"]
            raw_controls.append({
                "left_repeat": repeat + 1,
                "right_repeat": (repeat + 1) % 5 + 1,
                "session_id": request_key[0],
                "turn_id": request_key[1],
                "score_delta": delta,
                "material_regression": delta < -0.03,
            })

    tokenizer = None
    if args.tokenizer_path:
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(str(args.tokenizer_path), local_files_only=True)

    case_rows = []
    for repeat in range(5):
        baseline = raw_maps[repeat][(CASE_SESSION, CASE_TURN)]
        candidate = contract_maps[repeat][(CASE_SESSION, CASE_TURN)]
        raw_text = str(baseline.get("output_text", ""))
        candidate_text = str(candidate.get("output_text", ""))
        row: dict[str, Any] = {
            "repeat": repeat + 1,
            "request_class": contract_class(candidate),
            "requested_level": candidate.get("requested_level"),
            "effective_level": candidate.get("effective_level"),
            "certificate_issued": candidate.get("certificate_issued"),
            "certificate_scope_valid": candidate.get("certificate_scope_valid"),
            "moved_stable_tokens": candidate.get("moved_stable_tokens"),
            "raw_score": baseline["_score"],
            "contract_score": candidate["_score"],
            "score_delta": candidate["_score"] - baseline["_score"],
            "raw_output_sha256": sha256_bytes(raw_text.encode("utf-8")),
            "contract_output_sha256": sha256_bytes(candidate_text.encode("utf-8")),
            "first_character_divergence": text_divergence(raw_text, candidate_text),
            "raw_finish_reason": baseline.get("finish_reason"),
            "contract_finish_reason": candidate.get("finish_reason"),
        }
        if tokenizer:
            raw_ids = tokenizer.encode(raw_text, add_special_tokens=False)
            candidate_ids = tokenizer.encode(candidate_text, add_special_tokens=False)
            position = first_divergence(raw_ids, candidate_ids)
            row.update({
                "first_token_divergence": position,
                "raw_output_tokens": len(raw_ids),
                "contract_output_tokens": len(candidate_ids),
                "raw_token_at_divergence": (raw_ids[position]
                                             if position is not None and position < len(raw_ids) else None),
                "contract_token_at_divergence": (candidate_ids[position]
                                                  if position is not None and position < len(candidate_ids) else None),
            })
        case_rows.append(row)

    classes = ["admitted_compiled", "manifest_direct_l0", "runtime_fallback"]
    all_contract = [row for rows in contract_repeats for row in rows]
    tail_rows = [summarize_group(label, [row for row in all_contract
                                        if contract_class(row) == label], raw_maps)
                 for label in classes]
    tail_rows.append(summarize_group("overall_mixture", all_contract, raw_maps))

    material = [row for row in paired if row["material_regression"]]
    policy_material = [row for row in material if row["request_class"] == "admitted_compiled"]
    raw_material = [row for row in raw_controls if row["material_regression"]]
    quality_payload = {
        "schema_version": "contractkv.llama-quality-root-cause.v1",
        "case": {"session_id": CASE_SESSION, "turn_id": CASE_TURN},
        "protocol_sha256": sha256_bytes(args.protocol.read_bytes()),
        "matched_requests": len(paired),
        "observed_material_regressions": len(material),
        "observed_material_regression_rate": len(material) / max(1, len(paired)),
        "policy_attributable_material_regressions": len(policy_material),
        "policy_attributable_material_regression_rate": len(policy_material) / max(1, len(paired)),
        "raw_control_comparisons": len(raw_controls),
        "raw_control_material_regressions": len(raw_material),
        "raw_control_material_regression_rate": len(raw_material) / max(1, len(raw_controls)),
        "case_canary_decisions": [
            {"repeat": index + 1,
             "requested_level": row.get("requested_level"),
             "effective_level": row.get("effective_level"),
             "certificate_issued": row.get("certificate_issued"),
             "verify_decision": row.get("verify_decision"),
             "level_attempts": row.get("level_attempts", [])}
            for index, row in enumerate(canaries)
        ],
        "case_repeats": case_rows,
        "material_regressions": material,
        "raw_control_material_regressions_for_case": [
            row for row in raw_material
            if row["session_id"] == CASE_SESSION and row["turn_id"] == CASE_TURN
        ],
        "classification": "raw_fallback_nondeterminism_not_policy_attributable",
        "evidence": [
            "The affected request is L0 in every repeat after L2 and L1 verification fail closed.",
            "No certificate is issued, moved_stable_tokens is zero, and no compiled layout is served.",
            "The same frozen runner, model, dtype, concurrency, max_tokens, and prompt builder are used by both cells.",
            "Row-level generation/runtime hashes were not embedded in this historical matrix; this is recorded as an audit limitation rather than inferred.",
        ],
        "claim_boundary": (
            "Observed raw-vs-ContractKV output differences on fail-closed L0 requests are runtime-control "
            "variation. Only regressions on admitted_compiled requests are policy-attributable."
        ),
    }
    tail_payload = {
        "schema_version": "contractkv.llama-tail-stratification.v1",
        "rows": tail_rows,
        "claim_boundary": (
            "Per-class percentiles describe the five-repeat request mixture. The overall p95/p99 is not "
            "claimed as the tail of certified requests when fail-closed L0 requests dominate that quantile."
        ),
    }

    for path in (args.quality_output, args.tail_json, args.tail_csv):
        path.parent.mkdir(parents=True, exist_ok=True)
    args.quality_output.write_text(json.dumps(quality_payload, indent=2) + "\n", encoding="utf-8")
    args.tail_json.write_text(json.dumps(tail_payload, indent=2) + "\n", encoding="utf-8")
    with args.tail_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(tail_rows[0]))
        writer.writeheader()
        writer.writerows(tail_rows)
    print(json.dumps({
        "quality": {key: quality_payload[key] for key in (
            "observed_material_regressions", "policy_attributable_material_regressions",
            "raw_control_material_regressions", "classification")},
        "tail": tail_rows,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
