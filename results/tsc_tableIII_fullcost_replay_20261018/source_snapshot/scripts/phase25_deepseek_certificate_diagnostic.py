#!/usr/bin/env python3
"""Run a development-only DeepSeek layout-certificate failure diagnostic."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase17_live_common import generate_raw
from scripts.phase19b_end_to_end_live import compact_verify, load_jsonl, messages, turn_case
from scripts.phase22_llama_layout_ladder import expand_stable_segments, family_key, layout_for_level


def scalar_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in report.items()
        if not key.startswith("_") and isinstance(value, (str, int, float, bool, type(None)))
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--model-identity", required=True)
    parser.add_argument("--policy-hash", required=True)
    parser.add_argument("--load-tier", required=True)
    parser.add_argument("--stable-word-limit", type=int, default=1150)
    parser.add_argument("--stable-pieces", type=int, default=4)
    parser.add_argument("--max-tokens", type=int, default=128)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    ladder = {"L0": 0.0, "L1": 0.25, "L2": 0.5, "L3": 1.0}
    rows: list[dict[str, Any]] = []
    for sample in load_jsonl(args.sessions):
        session_id = str(sample["phase19b_session_id"])
        case = expand_stable_segments(turn_case(sample, 0, args.stable_word_limit), args.stable_pieces)
        raw_layout = layout_for_level(case, "L0", ladder)
        raw_messages = messages(case, raw_layout["topological_order"])
        try:
            raw = generate_raw(
                args.base_url,
                args.model,
                f"phase25-diagnostic-{args.load_tier}-{session_id}-raw",
                raw_messages,
                args.timeout,
                args.max_tokens,
            )
        except Exception as exc:
            for level in ("L1", "L2", "L3"):
                rows.append({
                    "model": args.model,
                    "session_id": session_id,
                    "family": family_key(sample),
                    "level": level,
                    "decision": "RAW_ERROR",
                    "failure_reason": f"{type(exc).__name__}: {exc}",
                })
            continue

        for level in ("L1", "L2", "L3"):
            layout = layout_for_level(case, level, ladder)
            base = {
                "model": args.model,
                "model_identity": args.model_identity,
                "session_id": session_id,
                "family": family_key(sample),
                "level": level,
                "raw_finish_reason": raw.get("finish_reason", ""),
                "raw_answer_tokens": len(raw.get("token_ids", [])),
                "moved_stable_tokens": int(layout.get("moved_stable_tokens", 0) or 0),
            }
            try:
                report = compact_verify(args, sample, case, layout, raw, session_id)
                rows.append({
                    **base,
                    **scalar_report(report),
                    "decision": report.get("verify_decision", report.get("decision", "INCOMPLETE")),
                })
            except Exception as exc:
                rows.append({
                    **base,
                    "decision": "INCOMPLETE",
                    "failure_reason": f"{type(exc).__name__}: {exc}",
                })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    print(json.dumps({
        "models": sorted({row["model"] for row in rows}),
        "sessions": len({row["session_id"] for row in rows}),
        "rows": len(rows),
        "pass": sum(row.get("decision") == "PASS" for row in rows),
        "fail": sum(row.get("decision") == "FAIL" for row in rows),
        "incomplete": sum(row.get("decision") not in {"PASS", "FAIL"} for row in rows),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
