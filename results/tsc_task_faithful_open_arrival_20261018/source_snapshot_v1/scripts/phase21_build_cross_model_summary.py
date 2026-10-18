#!/usr/bin/env python3
"""Build the Phase 21 cross-model evidence table from frozen result files."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def number(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = row.get(key)
    return default if value in {None, ""} else float(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qwen-summary", type=Path, required=True)
    parser.add_argument("--llama-summary", type=Path, required=True)
    parser.add_argument("--llama-audit", type=Path, required=True)
    parser.add_argument("--mistral-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    qwen_rows = read_csv(args.qwen_summary)
    qwen = next(row for row in qwen_rows
                if row["policy"] == "contractkv-full" and row["load_tier"] == "transition")
    qwen_raw = next(row for row in qwen_rows
                    if row["policy"] == "raw-order" and row["load_tier"] == "transition")

    llama_rows = read_csv(args.llama_summary)
    llama = next(row for row in llama_rows if row["policy"] == "contractkv-two-tier")
    llama_raw = next(row for row in llama_rows if row["policy"] == "raw-order")
    llama_audit = json.loads(args.llama_audit.read_text(encoding="utf-8"))

    mistral_data = json.loads(args.mistral_summary.read_text(encoding="utf-8"))
    mistral = mistral_data["contractkv"]
    mistral_raw = next(row for row in mistral_data["policies"] if row["policy"] == "raw-order")

    rows = [
        {
            "model": "Qwen3-8B",
            "evaluation_status": "positive_mainline",
            "future_requests": int(float(qwen["future_requests"])),
            "completion_rate": number(qwen, "completion_rate"),
            "safe_coverage": number(qwen, "certificate_issue_rate"),
            "unsafe_certified_sessions": 0,
            "fresh_future_recertification_rejections": 0,
            "future_quality_violation_rate": number(qwen, "quality_violation_rate"),
            "raw_mean_ttft_ms": number(qwen_raw, "mean_ttft_ms"),
            "contract_mean_ttft_ms": number(qwen, "mean_ttft_ms"),
            "contract_net_mean_ttft_ms": number(qwen, "net_mean_ttft_ms"),
            "net_mean_ttft_reduction_vs_raw": number(qwen, "net_ttft_reduction_vs_raw"),
            "raw_mean_new_prefill_tokens": number(qwen_raw, "mean_new_prefill_tokens"),
            "contract_mean_new_prefill_tokens": number(qwen, "mean_new_prefill_tokens"),
            "new_prefill_reduction_vs_raw": number(qwen, "new_prefill_reduction_vs_raw"),
            "certified_prefix_reuse_fraction": number(qwen, "certified_prefix_hit_fraction"),
            "max_dynamic_suffix_reuse_tokens": int(number(qwen, "max_dynamic_suffix_reuse_tokens")),
            "diagnosis": "mechanism_and_scoped_policy_pass",
        },
        {
            "model": "Llama-3.1-8B-Instruct",
            "evaluation_status": "mechanism_pass_stale_certificate_scope_fail",
            "future_requests": int(float(llama["requests"])),
            "completion_rate": number(llama, "completion_rate"),
            "safe_coverage": number(llama, "safe_coverage"),
            "unsafe_certified_sessions": int(number(llama, "unsafe_certified")),
            "fresh_future_recertification_rejections": int(llama_audit["fresh_rejected_or_incomplete"]),
            "future_quality_violation_rate": "",
            "raw_mean_ttft_ms": number(llama_raw, "mean_ttft_ms"),
            "contract_mean_ttft_ms": number(llama, "mean_ttft_ms"),
            "contract_net_mean_ttft_ms": "",
            "net_mean_ttft_reduction_vs_raw": number(llama, "net_ttft_reduction_vs_raw"),
            "raw_mean_new_prefill_tokens": number(llama_raw, "mean_new_prefill_tokens"),
            "contract_mean_new_prefill_tokens": number(llama, "mean_new_prefill_tokens"),
            "new_prefill_reduction_vs_raw": number(llama, "new_prefill_reduction_vs_raw"),
            "certified_prefix_reuse_fraction": number(llama, "certified_prefix_reuse_fraction"),
            "max_dynamic_suffix_reuse_tokens": int(number(llama, "max_dynamic_suffix_reuse_tokens")),
            "diagnosis": llama_audit["conclusion"],
        },
        {
            "model": "Mistral-7B-Instruct-v0.3",
            "evaluation_status": "positive_prospective_extension",
            "future_requests": int(mistral["requests"]),
            "completion_rate": mistral["completion_rate"],
            "safe_coverage": mistral["safe_coverage"],
            "unsafe_certified_sessions": mistral["unsafe_certified_sessions"],
            "fresh_future_recertification_rejections": 0,
            "future_quality_violation_rate": 0.0,
            "raw_mean_ttft_ms": mistral_raw["mean_ttft_ms"],
            "contract_mean_ttft_ms": mistral["mean_ttft_ms"],
            "contract_net_mean_ttft_ms": mistral["net_mean_ttft_ms"],
            "net_mean_ttft_reduction_vs_raw": mistral["net_mean_ttft_reduction_vs_raw"],
            "raw_mean_new_prefill_tokens": mistral_raw["mean_new_prefill_tokens"],
            "contract_mean_new_prefill_tokens": mistral["mean_new_prefill_tokens"],
            "new_prefill_reduction_vs_raw": mistral["new_prefill_reduction_vs_raw"],
            "certified_prefix_reuse_fraction": mistral["certified_stable_prefix_reuse_fraction"],
            "max_dynamic_suffix_reuse_tokens": mistral["max_dynamic_suffix_reuse_tokens"],
            "diagnosis": "mechanism_and_model_task_scoped_policy_pass",
        },
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
