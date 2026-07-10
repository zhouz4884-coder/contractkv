#!/usr/bin/env python3
"""Send repeated stable-context requests to gate Phase 14B instrumentation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12_prefix_cache_ab import send_chat_stream


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--context-repeats", type=int, default=800)
    args = parser.parse_args()
    stable = "The stable retrieval record is cacheable and must remain exact. " * args.context_repeats
    messages = [{"role": "user", "content": stable + "\nAnswer only: PREFIX_METRICS_OK. /no_think"}]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for run_id in range(args.repeats):
        result = send_chat_stream(
            args.base_url,
            args.model,
            messages,
            max_tokens=16,
            timeout=180,
            request_tag=f"phase14b-prefix-smoke-{run_id}",
        )
        result.update({"run_id": run_id, "context_repeats": args.context_repeats})
        rows.append(result)
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(f"smoke_requests={len(rows)} successes={sum(bool(row.get('success')) for row in rows)}")
    return 0 if all(row.get("success") for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
