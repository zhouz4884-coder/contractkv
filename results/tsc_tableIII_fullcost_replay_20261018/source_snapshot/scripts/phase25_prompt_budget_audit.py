#!/usr/bin/env python3
"""Audit a shared word cap against real model chat-template token budgets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from transformers import AutoTokenizer

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase19b_end_to_end_live import messages, turn_case
from scripts.phase22_llama_layout_ladder import expand_stable_segments, layout_for_level


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--sessions", type=Path, action="append", required=True)
    parser.add_argument("--word-caps", default="1500,1475,1450,1400")
    parser.add_argument("--input-budget", type=int, default=8064)
    parser.add_argument("--stable-pieces", type=int, default=4)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=True)
    sessions = [row for path in args.sessions for row in load_jsonl(path)]
    rows = []
    for cap in [int(value) for value in args.word_caps.split(",")]:
        lengths = []
        over = []
        for sample in sessions:
            case = expand_stable_segments(turn_case(sample, 0, cap), args.stable_pieces)
            layout = layout_for_level(case, "L0")
            rendered = tokenizer.apply_chat_template(
                messages(case, layout["topological_order"]), tokenize=True,
                add_generation_prompt=True,
            )
            length = len(rendered)
            lengths.append(length)
            if length > args.input_budget:
                over.append({
                    "session_id": sample.get("phase19b_session_id"),
                    "dataset": sample.get("dataset"), "task": sample.get("task"),
                    "sample_id": sample.get("sample_id"), "tokens": length,
                })
        rows.append({
            "word_cap": cap, "sessions": len(sessions), "input_budget": args.input_budget,
            "maximum_prompt_tokens": max(lengths, default=0),
            "over_budget_sessions": len(over), "over_budget_examples": over[:10],
            "pass": not over,
        })
    payload = {
        "schema_version": "contractkv.phase25.prompt-budget-audit.v1",
        "model_path": str(args.model_path), "rows": rows,
        "largest_safe_word_cap": next((row["word_cap"] for row in rows if row["pass"]), None),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["largest_safe_word_cap"] is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
