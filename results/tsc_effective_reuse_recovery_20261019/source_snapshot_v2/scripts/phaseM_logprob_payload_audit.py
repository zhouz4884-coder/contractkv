#!/usr/bin/env python3
"""Inspect frozen top-2 Mistral logprob payloads without changing top-k."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12e_cache_aware_posc import SegmentPrefixLedger
from scripts.phase16r_verifier_live import extract_raw_tokens_and_margins
from scripts.phase17_live_common import post_json
from scripts.phase19b_end_to_end_live import compile_layout, messages, turn_case
from scripts.phase20b_llama_rejection_audit import load_jsonl


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--base-url", required=True); parser.add_argument("--model", required=True)
    parser.add_argument("--session-id", required=True); parser.add_argument("--max-tokens", type=int, default=128)
    parser.add_argument("--stable-word-limit", type=int, default=1500)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sample = next(row for row in load_jsonl(args.sessions)
                  if str(row["phase19b_session_id"]) == args.session_id)
    case = turn_case(sample, 0, args.stable_word_limit)
    layout = compile_layout("raw-order", case, SegmentPrefixLedger(), args.session_id, 0, 2000)
    response = post_json(args.base_url.rstrip("/") + "/chat/completions", {
        "model": args.model, "messages": messages(case, layout["topological_order"]),
        "max_tokens": args.max_tokens, "temperature": 0, "top_p": 1,
        "logprobs": True, "top_logprobs": 2, "return_token_ids": True,
        "request_id": f"mistral-logprob-audit-{args.session_id}",
    }, args.timeout)
    content = (((response.get("choices") or [{}])[0].get("logprobs") or {}).get("content") or [])
    problematic = []
    for index, item in enumerate(content):
        chosen_token = item.get("token")
        candidates = item.get("top_logprobs") or []
        competitors = [candidate for candidate in candidates
                       if candidate.get("logprob") is not None and candidate.get("token") != chosen_token]
        if not competitors:
            problematic.append({"index": index, "chosen": item,
                                "candidate_count": len(candidates),
                                "same_text_count": sum(candidate.get("token") == chosen_token for candidate in candidates),
                                "candidate_keys": sorted({key for candidate in candidates for key in candidate})})
    try:
        token_ids, margins, finish_reason, source = extract_raw_tokens_and_margins(response)
        parser_pass = True; parser_error = ""
    except Exception as exc:
        token_ids = []; margins = []; finish_reason = ""; source = ""
        parser_pass = False; parser_error = f"{type(exc).__name__}: {exc}"
    result = {"schema_version": "mistral.logprob-payload-audit.v1",
              "session_id": args.session_id, "tokens": len(content),
              "problematic_positions": len(problematic),
              "problematic_examples": problematic[:8],
              "current_parser_pass": parser_pass,
              "current_parser_error": parser_error,
              "parsed_token_count": len(token_ids),
              "parsed_margin_count": len(margins),
              "finish_reason": finish_reason, "token_source": source,
              "top_logprobs_frozen": 2,
              "claim_boundary": "Development-only payload inspection; no top-k change."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
