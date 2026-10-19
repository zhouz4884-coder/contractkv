#!/usr/bin/env python3
"""Audit Mistral tokenizer, template, terminal token, and teacher-forced identity."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from transformers import AutoTokenizer

from scripts.phase19b_end_to_end_live import compile_layout, messages, turn_case
from scripts.phase20b_llama_rejection_audit import audit_one, hash_ids, load_jsonl
from scripts.phase12e_cache_aware_posc import SegmentPrefixLedger


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--base-url", required=True); parser.add_argument("--model", required=True)
    parser.add_argument("--repeats", type=int, default=3); parser.add_argument("--max-tokens", type=int, default=128)
    parser.add_argument("--stable-word-limit", type=int, default=2600)
    parser.add_argument("--tool-slack-ms", type=float, default=2000)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    args = parser.parse_args()
    sessions = load_jsonl(args.sessions)
    by_family: dict[str, list[dict[str, Any]]] = {}
    for sample in sessions:
        by_family.setdefault(str(sample["mistral_family"]), []).append(sample)
    selected = [sample for family in sorted(by_family) for sample in by_family[family][:2]]
    tokenizer = AutoTokenizer.from_pretrained(str(args.model_path), local_files_only=True)
    rows = []
    for sample in selected:
        row = audit_one(args, sample)
        # Mistral's template ends the user turn with [/INST]; unlike the
        # Llama template, add_generation_prompt=True legitimately appends no
        # extra IDs.  Exact forced-prefix and offset equality are the relevant
        # invariants, so an empty but frozen suffix is not a mismatch.
        if (row.get("candidate_generation_suffix_hash") == hash_ids([])
                and row.get("prompt_prefix_match") is True
                and row.get("verify_offset_match") is True):
            row["protocol_bug"] = False
            if row.get("taxonomy") == "PROMPT_SUFFIX_MISMATCH":
                row["taxonomy"] = "TEMPLATE_EMPTY_SUFFIX_VALID"
        sid = str(sample["phase19b_session_id"])
        case = turn_case(sample, 0, args.stable_word_limit)
        layout = compile_layout("physical-cache-aware", case, SegmentPrefixLedger(), sid, 0,
                                args.tool_slack_ms)
        ordered = {str(segment["segment_id"]): segment for segment in case["segments"]}
        boundaries = []
        order = [str(value) for value in layout["topological_order"]]
        for left_id, right_id in zip(order, order[1:]):
            left = str(ordered[left_id].get("text", ""))
            right = str(ordered[right_id].get("text", ""))
            joined = left[-32:] + "\n\n" + right[:32]
            boundaries.append({"left_id": left_id, "right_id": right_id,
                               "left_tail": left[-32:], "right_head": right[:32],
                               "joined_token_ids": tokenizer.encode(joined, add_special_tokens=False)})
        rendered = tokenizer.apply_chat_template(
            messages(case, order), tokenize=False, add_generation_prompt=True)
        rendered_ids = tokenizer.apply_chat_template(
            messages(case, order), tokenize=True, add_generation_prompt=True)
        row["segment_boundary_separator"] = "\\n\\n"
        row["segment_boundary_windows"] = boundaries
        row["rendered_prompt_tail"] = rendered[-256:]
        row["rendered_prompt_tokens"] = len(rendered_ids)
        rows.append(row)
    summary = {
        "schema_version": "mistral.protocol-audit.v1", "cases": len(rows),
        "protocol_bug_count": sum(bool(row.get("protocol_bug")) for row in rows),
        "nondeterministic_count": sum(not bool(row.get("candidate_repeats_deterministic", False)) for row in rows),
        "length_stop_count": sum(row.get("taxonomy") == "LENGTH_STOP" for row in rows),
        "prompt_identity_pass_count": sum(bool(row.get("prompt_prefix_match")) and bool(row.get("verify_offset_match")) for row in rows),
        "max_rendered_prompt_tokens": max([int(row.get("rendered_prompt_tokens", 0) or 0) for row in rows], default=0),
        "all_boundaries_use_frozen_separator": all(row.get("segment_boundary_separator") == "\\n\\n" for row in rows),
    }
    summary["gate_pass"] = (summary["protocol_bug_count"] == 0
                            and summary["nondeterministic_count"] == 0
                            and summary["prompt_identity_pass_count"] == len(rows))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    args.summary_output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
