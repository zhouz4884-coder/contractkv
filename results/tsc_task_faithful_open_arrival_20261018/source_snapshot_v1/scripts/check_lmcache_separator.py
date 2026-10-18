#!/usr/bin/env python3
"""Verify that an LMCache blend separator survives a model chat template."""

from __future__ import annotations

import argparse
import json

from transformers import AutoTokenizer


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--separator", default=" # # ")
    parser.add_argument("--search", action="store_true")
    args = parser.parse_args()
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    candidates = [args.separator]
    if args.search:
        candidates = [
            " # # ", "\n# #\n", "\n\n# #\n\n", "\n<BLEND_SEP>\n",
            "\n[BLEND_SEP]\n", "\n### SEGMENT ###\n", "<|reserved_special_token_0|>",
        ]
    results = []
    for separator in candidates:
        separator_ids = tokenizer.encode(separator)[1:]
        prompt_ids = tokenizer.apply_chat_template(
            [{"role": "user", "content": "alpha" + separator + "beta"}],
            tokenize=True,
            add_generation_prompt=True,
        )
        offsets = [
            index for index in range(len(prompt_ids) - len(separator_ids) + 1)
            if prompt_ids[index:index + len(separator_ids)] == separator_ids
        ]
        results.append({
            "separator": separator,
            "separator_ids": separator_ids,
            "decoded_separator": tokenizer.decode(separator_ids),
            "chat_template_match_offsets": offsets,
            "pass": bool(separator_ids and offsets),
        })
    print(json.dumps(results if args.search else results[0], indent=2))
    return 0 if any(result["pass"] for result in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
