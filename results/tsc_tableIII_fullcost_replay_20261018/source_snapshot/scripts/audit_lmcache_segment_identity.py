#!/usr/bin/env python3
"""Audit token-level LMCache segment identity across two future turns."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase19b_end_to_end_live import load_jsonl, turn_case
from scripts.phase22_llama_broad_live import expand_stable_segments
from scripts.phase22_llama_layout_ladder import layout_for_level
from scripts.run_external_llama_radix_replay import request_messages


def split(ids: list[int], separator: list[int]) -> list[list[int]]:
    matches = []
    for index in range(len(ids) - len(separator) + 1):
        if ids[index:index + len(separator)] == separator:
            matches.append(index)
    chunks = []
    start = 0
    for index in matches:
        chunks.append(ids[start:index])
        start = index + len(separator)
    chunks.append(ids[start:])
    return chunks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--separator", default="\n# #\n")
    parser.add_argument("--session-index", type=int, default=0)
    args = parser.parse_args()
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    sample = load_jsonl(args.sessions)[args.session_index]
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    ladder = {key: float(value) for key, value in manifest["layout_ladder"].items()}
    sep_ids = tokenizer.encode(args.separator)[1:]
    rows = []
    all_chunks = []
    for turn in (0, 1):
        case = expand_stable_segments(turn_case(sample, turn, 1500), 16)
        order = layout_for_level(case, "L0", ladder)["topological_order"]
        messages = request_messages(case, order, args.separator)
        ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True)
        chunks = split(ids, sep_ids)
        all_chunks.append(chunks)
        rows.append({
            "turn": turn,
            "prompt_tokens": len(ids),
            "separator_matches": len(chunks) - 1,
            "chunk_lengths": [len(chunk) for chunk in chunks],
            "first_chunk_preview": tokenizer.decode(chunks[0])[:240],
        })
    equal = [left == right for left, right in zip(all_chunks[0], all_chunks[1])]
    result = {
        "session_id": sample.get("phase19b_session_id"),
        "separator_ids": sep_ids,
        "turns": rows,
        "paired_chunks": min(len(all_chunks[0]), len(all_chunks[1])),
        "equal_chunk_indices": [index for index, value in enumerate(equal) if value],
        "first_chunk_equal": bool(equal and equal[0]),
        "stable_chunks_after_dynamic_equal": sum(equal[2:]) if len(equal) > 2 else 0,
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
