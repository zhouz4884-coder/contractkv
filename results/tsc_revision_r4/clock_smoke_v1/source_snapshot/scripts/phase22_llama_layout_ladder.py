#!/usr/bin/env python3
"""Task-agnostic progressive layout ladder for broad Llama qualification."""

from __future__ import annotations

import math
import re
from copy import deepcopy
from typing import Any

from scripts.phase12_posc_layout_compiler import validate_topological_order


LEVEL_FRACTIONS = {"L0": 0.0, "L1": 0.25, "L2": 0.50, "L3": 1.0}
VOLATILE_TYPES = {"TOOL_OBS", "USER_QUERY", "CHAT_HISTORY", "SCRATCHPAD"}


def split_text_preserving(text: str, pieces: int) -> list[str]:
    """Split at token-like boundaries while preserving every source character."""
    if pieces <= 1 or not text:
        return [text]
    matches = list(re.finditer(r"\S+\s*", text))
    if not matches:
        return [text]
    units = []
    cursor = 0
    for match in matches:
        units.append(text[cursor:match.end()])
        cursor = match.end()
    if cursor < len(text):
        units[-1] += text[cursor:]
    width = max(1, math.ceil(len(units) / pieces))
    chunks = ["".join(units[start:start + width]) for start in range(0, len(units), width)]
    assert "".join(chunks) == text
    return chunks


def expand_stable_segments(case: dict[str, Any], pieces: int = 4) -> dict[str, Any]:
    """Create contiguous stable units without inspecting dataset or task names."""
    source = deepcopy(case)
    system = next(segment for segment in source["segments"] if segment["segment_type"] == "SYS_PROMPT")
    tool = next(segment for segment in source["segments"] if segment["segment_type"] == "TOOL_OBS")
    query = next(segment for segment in source["segments"] if segment["segment_type"] == "USER_QUERY")
    stable = [segment for segment in source["segments"]
              if segment["segment_type"] not in VOLATILE_TYPES | {"SYS_PROMPT"}]

    expanded: list[dict[str, Any]] = []
    for segment in stable:
        chunks = split_text_preserving(str(segment.get("text", "")), pieces)
        source_tokens = max(1, int(segment.get("token_count") or 1))
        source_chars = max(1, len(str(segment.get("text", ""))))
        for index, chunk in enumerate(chunks):
            copy = dict(segment)
            copy["segment_id"] = f"{segment['segment_id']}__p{index}"
            copy["text"] = chunk
            copy["token_count"] = max(1, round(source_tokens * len(chunk) / source_chars))
            expanded.append(copy)

    sys_copy = dict(system)
    sys_copy["dependencies"] = []
    previous = str(sys_copy["segment_id"])
    for segment in expanded:
        segment["dependencies"] = [previous]
        previous = str(segment["segment_id"])
    tool_copy = dict(tool)
    tool_copy["dependencies"] = [str(sys_copy["segment_id"])]
    query_copy = dict(query)
    query_copy["dependencies"] = list(dict.fromkeys([previous, str(tool_copy["segment_id"])]))
    source["segments"] = [sys_copy, tool_copy, *expanded, query_copy]
    source["ladder_stable_segment_ids"] = [str(segment["segment_id"]) for segment in expanded]
    return source


def layout_for_level(
    case: dict[str, Any], level: str, level_fractions: dict[str, float] | None = None,
) -> dict[str, Any]:
    fractions = level_fractions or LEVEL_FRACTIONS
    if level not in fractions:
        raise ValueError(f"unknown layout level: {level}")
    by_id = {str(segment["segment_id"]): segment for segment in case["segments"]}
    system = next(str(segment["segment_id"]) for segment in case["segments"]
                  if segment["segment_type"] == "SYS_PROMPT")
    tool = next(str(segment["segment_id"]) for segment in case["segments"]
                if segment["segment_type"] == "TOOL_OBS")
    query = next(str(segment["segment_id"]) for segment in case["segments"]
                 if segment["segment_type"] == "USER_QUERY")
    stable = list(case.get("ladder_stable_segment_ids") or [
        str(segment["segment_id"]) for segment in case["segments"]
        if segment["segment_type"] not in VOLATILE_TYPES | {"SYS_PROMPT"}
    ])
    total = sum(int(by_id[sid].get("token_count") or 0) for sid in stable)
    target = total * fractions[level]
    moved: list[str] = []
    accumulated = 0
    if target > 0:
        for sid in stable:
            moved.append(sid)
            accumulated += int(by_id[sid].get("token_count") or 0)
            if accumulated >= target:
                break
    remaining = stable[len(moved):]
    order = [system, *moved, tool, *remaining, query]
    violations = validate_topological_order(order, case["segments"])
    if violations:
        raise ValueError(f"invalid progressive layout {level}: {violations}")
    return {
        "policy": f"llama-broad-{level.lower()}",
        "selected_policy": level,
        "layout_level": level,
        "topological_order": order,
        "violated_edges": violations,
        "moved_stable_tokens": accumulated,
        "total_stable_tokens": total,
        "moved_fraction": accumulated / max(1, total),
        "reason": "task_agnostic_progressive_stable_prefix",
    }


def family_key(sample: dict[str, Any]) -> str:
    return f"{sample.get('dataset', '')}:{sample.get('task', '')}"
