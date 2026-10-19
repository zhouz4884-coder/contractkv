#!/usr/bin/env python3
"""Segment parser for ContractKV Python-level serving prototype."""

from __future__ import annotations

import re
import time
import uuid
from typing import Any


TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def approximate_token_count(text: str) -> int:
    if not text:
        return 0
    tokens = TOKEN_RE.findall(text)
    return max(1, len(tokens))


def _segment(segment_type: str, text: str) -> dict[str, Any]:
    return {"type": segment_type, "text": text, "token_count": approximate_token_count(text)}


def _split_user_content(content: str) -> list[dict[str, Any]]:
    lowered = content.lower()
    if "context:" in lowered and "question:" in lowered:
        before_question, question = re.split(r"(?i)\bquestion\s*:", content, maxsplit=1)
        context = re.sub(r"(?i)^\s*context\s*:\s*", "", before_question).strip()
        return [_segment("RAG_CHUNK", context), _segment("USER_QUERY", question.strip())]
    if "repo" in lowered or "def " in content or "class " in content:
        return [_segment("REPO_CONTEXT", content)]
    if len(content) > 2000:
        return [_segment("RAG_CHUNK", content)]
    return [_segment("USER_QUERY", content)]


def parse_chat_segments(request: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    segments: list[dict[str, Any]] = []
    messages = request.get("messages", [])
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")
        if not isinstance(content, str):
            content = str(content)
        if role == "system":
            segments.append(_segment("SYS_PROMPT", content))
        elif role == "assistant":
            segments.append(_segment("ASSISTANT_HISTORY", content))
        elif role == "tool":
            segments.append(_segment("TOOL_OBSERVATION", content))
        else:
            segments.extend(_split_user_content(content))

    total_prompt_tokens = sum(int(segment["token_count"]) for segment in segments)
    return {
        "dataset": request.get("contractkv_dataset", "runtime"),
        "task": request.get("contractkv_task", "openai_chat"),
        "sample_id": str(request.get("contractkv_sample_id", request.get("request_id", uuid.uuid4().hex[:12]))),
        "total_prompt_tokens": total_prompt_tokens,
        "segments": segments,
        "answer": "",
        "metadata": {
            "source": "contractkv_proxy",
            "model": request.get("model", ""),
            "parse_ms": round((time.perf_counter() - started) * 1000, 6),
        },
    }
