#!/usr/bin/env python3
"""Backfill tokenizer-exact stable-prefix boundaries without loading weights."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.contractkv_pstp import lcp_length
from scripts.phase19b_end_to_end_live import load_jsonl, messages, stable_order, turn_case
from scripts.phase22_llama_layout_ladder import expand_stable_segments, layout_for_level


def token_ids(tokenizer: Any, value: list[dict[str, str]]) -> list[int]:
    return [int(item) for item in tokenizer.apply_chat_template(
        value, tokenize=True, add_generation_prompt=True)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--stable-word-limit", type=int, default=1150)
    args = parser.parse_args()
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=True)
    samples = {str(row["phase19b_session_id"]): row for row in load_jsonl(args.sessions)}
    rows = load_jsonl(args.audit)
    cache: dict[tuple[str, str], tuple[int, int]] = {}
    for row in rows:
        key = (str(row["session_id"]), str(row["level"]))
        if key not in cache:
            case = expand_stable_segments(
                turn_case(samples[key[0]], 0, args.stable_word_limit), 4)
            layout = layout_for_level(case, key[1])
            order = [str(value) for value in layout["topological_order"]]
            prompt = token_ids(tokenizer, messages(case, order))
            prefix = token_ids(tokenizer, messages(case, stable_order(case, order)))
            cache[key] = (lcp_length(prefix, prompt), len(prompt))
        stable, prompt = cache[key]
        row["tokenizer_exact_stable_prefix_tokens"] = stable
        row["tokenizer_exact_candidate_prompt_tokens"] = prompt
    args.audit.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(json.dumps({"rows": len(rows), "minimum_stable": min(v[0] for v in cache.values()),
                      "maximum_stable": max(v[0] for v in cache.values())}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
