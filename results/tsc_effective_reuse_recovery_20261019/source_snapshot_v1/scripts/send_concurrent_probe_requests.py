#!/usr/bin/env python3
"""Send concurrent long prompts to a vLLM OpenAI endpoint for pressure observation."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import time
import urllib.request
from pathlib import Path


def make_prompt(target_words: int, request_index: int) -> str:
    filler = ("alpha beta gamma delta epsilon zeta eta theta " * ((target_words // 8) + 1))[: target_words * 6]
    return f"/no_think Pressure request {request_index}. Read the context and answer OK.\n\n{filler}\n\nAnswer OK."


def send_one(base_url: str, model: str, prompt: str, max_tokens: int, timeout: float, request_index: int) -> dict:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0,
    }
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
        return {
            "request_index": request_index,
            "success": True,
            "latency_ms": round((time.perf_counter() - start) * 1000, 6),
            "response_bytes": len(body),
            "error_type": "none",
            "error_message": "",
        }
    except Exception as exc:
        return {
            "request_index": request_index,
            "success": False,
            "latency_ms": round((time.perf_counter() - start) * 1000, 6),
            "response_bytes": 0,
            "error_type": type(exc).__name__,
            "error_message": str(exc)[:300],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--num-requests", type=int, default=8)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--target-words", type=int, default=6000)
    parser.add_argument("--max-tokens", type=int, default=16)
    parser.add_argument("--timeout", type=float, default=240)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prompts = [make_prompt(args.target_words, i) for i in range(args.num_requests)]
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [
            pool.submit(send_one, args.base_url, args.model, prompt, args.max_tokens, args.timeout, i)
            for i, prompt in enumerate(prompts)
        ]
        for future in concurrent.futures.as_completed(futures):
            row = future.result()
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as f:
        for row in sorted(rows, key=lambda item: item["request_index"]):
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return 0 if any(row["success"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
