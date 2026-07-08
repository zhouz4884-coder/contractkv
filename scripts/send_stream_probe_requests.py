#!/usr/bin/env python3
"""Send streaming long prompts to a vLLM OpenAI endpoint."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import time
import urllib.request
from pathlib import Path
from typing import Any


def make_prompt(target_words: int, request_index: int) -> str:
    chunk = "alpha beta gamma delta epsilon zeta eta theta "
    words = (chunk.split() * ((target_words // 8) + 2))[:target_words]
    filler = " ".join(words)
    return f"/no_think Pressure request {request_index}. Read the context and answer OK.\n\n{filler}\n\nAnswer OK."


def _iter_sse(response: Any):
    for raw in response:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        yield json.loads(payload)


def send_one(base_url: str, model: str, prompt: str, max_tokens: int, timeout: float, request_index: int) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": True,
    }
    request = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    first_token = None
    last_token = None
    output_tokens = 0
    output_chunks: list[str] = []
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            for chunk in _iter_sse(response):
                content = chunk.get("choices", [{}])[0].get("delta", {}).get("content") or ""
                if not content:
                    continue
                now = time.perf_counter()
                if first_token is None:
                    first_token = now
                last_token = now
                output_tokens += 1
                output_chunks.append(content)
        ended = time.perf_counter()
        ttft_ms = (first_token - started) * 1000.0 if first_token is not None else 0.0
        tpot_ms = ((last_token - first_token) * 1000.0 / max(output_tokens - 1, 1)) if first_token and last_token and output_tokens > 1 else 0.0
        output_text = "".join(output_chunks)
        return {
            "request_index": request_index,
            "success": bool(output_text),
            "ttft_ms": round(ttft_ms, 6),
            "tpot_ms": round(tpot_ms, 6),
            "total_latency_ms": round((ended - started) * 1000.0, 6),
            "output_tokens": output_tokens,
            "response_bytes": len(output_text.encode("utf-8")),
            "output_text": output_text,
            "error_type": "none" if output_text else "bad_output",
            "error_message": "",
        }
    except Exception as exc:
        ended = time.perf_counter()
        return {
            "request_index": request_index,
            "success": False,
            "ttft_ms": 0.0,
            "tpot_ms": 0.0,
            "total_latency_ms": round((ended - started) * 1000.0, 6),
            "output_tokens": 0,
            "response_bytes": 0,
            "output_text": "",
            "error_type": type(exc).__name__,
            "error_message": str(exc)[:300],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--num-requests", type=int, default=1)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--target-words", type=int, default=5000)
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
    return 0 if rows and all(row["error_type"] == "none" for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
