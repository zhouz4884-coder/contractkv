#!/usr/bin/env python3
"""Minimal same-backend teacher-forced verifier through vLLM Chat API."""

from __future__ import annotations

import argparse
import csv
import json
import urllib.request
from pathlib import Path
from typing import Any


FIELDS = [
    "case_id", "layout", "raw_success", "verify_success", "answer_tokens",
    "top1_matched_tokens", "top1_match_rate", "min_top1_margin",
    "certificate_pass", "raw_output", "error", "claim_boundary",
]


def post_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def build_messages(case_id: int, layout: str) -> tuple[list[dict[str, str]], str]:
    marker = f"PHASE16C_OK_{case_id}"
    stable = " ".join(f"stable_fact_{case_id}_{index}" for index in range(160))
    tool = f"[TOOL_OBS] transient status for case {case_id}: no new answer evidence."
    stable_block = f"[STABLE_CONTEXT]\n{stable}"
    if layout == "candidate":
        user = f"{stable_block}\n{tool}\nReturn exactly this marker: {marker}"
    else:
        user = f"{tool}\n{stable_block}\nReturn exactly this marker: {marker}"
    return [
        {"role": "system", "content": "/no_think Reply with only the requested marker."},
        {"role": "user", "content": user},
    ], marker


def extract_output(response: dict[str, Any]) -> str:
    choices = response.get("choices") or []
    if not choices:
        return ""
    return str(choices[0].get("message", {}).get("content") or "")


def token_rank_and_margin(entry: Any, token_id: int) -> tuple[int | None, float | None]:
    if not isinstance(entry, dict):
        return None, None
    values = []
    actual = None
    for key, value in entry.items():
        if not isinstance(value, dict):
            continue
        logprob = value.get("logprob")
        rank = value.get("rank")
        if logprob is not None:
            values.append(float(logprob))
        try:
            matches = int(key) == token_id
        except (TypeError, ValueError):
            matches = str(value.get("decoded_token", "")) == str(token_id)
        if matches:
            actual = (int(rank) if rank is not None else None, float(logprob) if logprob is not None else None)
    if actual is None:
        return None, None
    rank, actual_logprob = actual
    alternatives = sorted((value for value in values if value != actual_logprob), reverse=True)
    margin = actual_logprob - alternatives[0] if actual_logprob is not None and alternatives else None
    return rank, margin


def verify_case(base_url: str, model: str, case_id: int, timeout: float) -> dict[str, Any]:
    raw_messages, marker = build_messages(case_id, "raw")
    candidate_messages, _ = build_messages(case_id, "candidate")
    try:
        raw = post_json(base_url.rstrip("/") + "/chat/completions", {
            "model": model, "messages": raw_messages, "max_tokens": 16,
            "temperature": 0, "stream": False,
            "request_id": f"phase16c-raw-{case_id}",
        }, timeout)
        output = extract_output(raw)
        if not output:
            raise RuntimeError("raw generation returned no output")

        api_root = base_url.rstrip("/")
        if api_root.endswith("/v1"):
            api_root = api_root[:-3]
        base_tokens = post_json(api_root + "/tokenize", {
            "model": model, "messages": candidate_messages,
            "add_generation_prompt": True,
        }, timeout).get("tokens", [])
        full_messages = [*candidate_messages, {"role": "assistant", "content": output}]
        verified = post_json(base_url.rstrip("/") + "/chat/completions", {
            "model": model, "messages": full_messages, "max_tokens": 1,
            "temperature": 0, "stream": False, "prompt_logprobs": 2,
            "return_token_ids": True, "continue_final_message": True,
            "add_generation_prompt": False,
            "request_id": f"contractkv-shadow-abort-teacher-{case_id}",
            "priority": 100,
        }, timeout)
        prompt_ids = verified.get("prompt_token_ids") or []
        prompt_logprobs = verified.get("prompt_logprobs") or []
        prefix = 0
        for left, right in zip(base_tokens, prompt_ids):
            if left != right:
                break
            prefix += 1
        answer_ids = prompt_ids[prefix:]
        ranks = []
        margins = []
        for index, token_id in enumerate(answer_ids, start=prefix):
            entry = prompt_logprobs[index] if index < len(prompt_logprobs) else None
            rank, margin = token_rank_and_margin(entry, int(token_id))
            ranks.append(rank)
            if margin is not None:
                margins.append(margin)
        matched = sum(rank == 1 for rank in ranks)
        passed = bool(answer_ids and matched == len(answer_ids) and marker in output)
        return {
            "case_id": case_id, "layout": "raw_to_candidate",
            "raw_success": True, "verify_success": bool(prompt_logprobs),
            "answer_tokens": len(answer_ids), "top1_matched_tokens": matched,
            "top1_match_rate": matched / max(len(answer_ids), 1),
            "min_top1_margin": min(margins) if margins else "",
            "certificate_pass": passed, "raw_output": output,
            "error": "",
            "claim_boundary": "Same vLLM backend prompt-logprob teacher forcing; marker cases, no EOS/stop certificate and no full task benchmark.",
        }
    except Exception as exc:
        return {
            "case_id": case_id, "layout": "raw_to_candidate",
            "raw_success": False, "verify_success": False, "answer_tokens": 0,
            "top1_matched_tokens": 0, "top1_match_rate": 0,
            "min_top1_margin": "", "certificate_pass": False,
            "raw_output": "", "error": str(exc)[:500],
            "claim_boundary": "Same vLLM backend prompt-logprob teacher forcing; marker cases, no EOS/stop certificate and no full task benchmark.",
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8016/v1")
    parser.add_argument("--model", default="qwen3-4b")
    parser.add_argument("--cases", type=int, default=12)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--output", type=Path, default=Path("results/hard_systems/phase16c_vllm_teacher_forced_probe_v0.csv"))
    args = parser.parse_args()
    rows = [verify_case(args.base_url, args.model, case_id, args.timeout) for case_id in range(args.cases)]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
