#!/usr/bin/env python3
"""Build Phase 12E multi-turn agent trajectories."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _seg(segment_id: str, segment_type: str, text: str, deps: list[str], volatility: float, cache_stability: float) -> dict[str, Any]:
    return {
        "segment_id": segment_id,
        "segment_type": segment_type,
        "text": text,
        "token_count": max(1, len(text.split())),
        "dependencies": deps,
        "volatility": volatility,
        "cache_stability": cache_stability,
        "reuse_probability": cache_stability,
        "boundary_risk": 0.0,
        "stability_scope": "cross_turn" if cache_stability >= 0.5 else "single_turn",
    }


def _edges(segments: list[dict[str, Any]]) -> list[list[str]]:
    return [[dep, str(segment["segment_id"])] for segment in segments for dep in segment.get("dependencies", [])]


def _pad(label: str, words: int) -> str:
    base = f"{label} cache contract lifecycle prefix block stable segment ".split()
    return " ".join((base * ((words // len(base)) + 2))[:words])


def _code_turn(i: int, turn: int) -> dict[str, Any]:
    marker = f"CAPOSC_CODE_{i}_{turn}"
    segments = [
        _seg("sys", "SYS_PROMPT", "Preserve repository dependency order and answer with the marker only. /no_think", [], 0.0, 1.0),
        _seg("tool_obs_current", "TOOL_OBS", f"Current turn tool observation {turn} for code trajectory {i}: volatile run state.", ["sys"], 1.0, 0.0),
        _seg("repo_import", "REPO_IMPORT", f"IMPORT SECTION: imports BASE_{i}. {_pad('import', 120)}", ["sys"], 0.0, 1.0),
        _seg("repo_class", "REPO_CLASS", f"CLASS SECTION: Planner_{i} extends BASE_{i}. {_pad('class', 180)}", ["repo_import"], 0.0, 1.0),
    ]
    for t in range(2, turn + 1):
        segments.append(
            _seg(
                f"repo_function_{t}",
                "REPO_FUNCTION",
                f"FUNCTION SECTION {t}: function_{t} uses Planner_{i} and returns {marker} when asked on turn {turn}. {_pad('function', 120)}",
                ["repo_class"] if t == 2 else [f"repo_function_{t - 1}"],
                0.0,
                1.0,
            )
        )
    final_dep = f"repo_function_{turn}" if turn >= 2 else "repo_class"
    segments.append(_seg("query", "USER_QUERY", f"Return marker {marker}. If dependency order is broken, return ORDER_ERROR.", [final_dep, "tool_obs_current"], 0.1, 0.0))
    return {
        "trajectory_id": f"code_{i}",
        "turn_id": turn,
        "case_type": "code_agent",
        "expected_answer": marker,
        "unsafe_answer": "ORDER_ERROR",
        "tool_slack_ms": [0, 50, 100, 200, 500, 100][turn % 6],
        "segments": segments,
        "dependency_edges": _edges(segments),
    }


def _rag_turn(i: int, turn: int) -> dict[str, Any]:
    marker = f"CAPOSC_RAG_{i}"
    segments = [
        _seg("sys", "SYS_PROMPT", "Answer from stable documents with the marker only. /no_think", [], 0.0, 1.0),
        _seg("doc_a", "RAG_CHUNK", f"Stable document A contains marker {marker}. {_pad('doca', 200)}", ["sys"], 0.0, 1.0),
        _seg("doc_b", "RAG_CHUNK", f"Stable document B is independent retrieval context. {_pad('docb', 160)}", ["sys"], 0.0, 1.0),
        _seg("tool_obs_current", "TOOL_OBS", f"Current RAG tool observation for turn {turn}: no new evidence.", ["sys"], 1.0, 0.0),
    ]
    for t in range(1, turn + 1):
        if t >= 3:
            segments.append(_seg(f"doc_extra_{t}", "RAG_CHUNK", f"Stable extra retrieval chunk {t}. {_pad('extra', 80)}", ["sys"], 0.0, 1.0))
    segments.append(_seg("query", "USER_QUERY", f"Return marker {marker}.", ["doc_a", "doc_b", "tool_obs_current"], 0.1, 0.0))
    return {
        "trajectory_id": f"rag_{i}",
        "turn_id": turn,
        "case_type": "rag_agent",
        "expected_answer": marker,
        "unsafe_answer": "ORDER_ERROR",
        "tool_slack_ms": [0, 50, 100, 200, 500, 100][turn % 6],
        "segments": segments,
        "dependency_edges": _edges(segments),
    }


def _mixed_turn(i: int, turn: int) -> dict[str, Any]:
    marker = f"CAPOSC_MIXED_{i}"
    segments = [
        _seg("sys", "SYS_PROMPT", "Use repository and document context. Preserve repository order. /no_think", [], 0.0, 1.0),
        _seg("tool_obs_1", "TOOL_OBS", f"Initial dynamic observation for mixed task {i}.", ["sys"], 1.0, 0.0),
        _seg("repo_import", "REPO_IMPORT", f"IMPORT SECTION: defines MIX_BASE_{i}. {_pad('miximport', 100)}", ["sys"], 0.0, 1.0),
        _seg("repo_class", "REPO_CLASS", f"CLASS SECTION: uses MIX_BASE_{i}. {_pad('mixclass', 140)}", ["repo_import"], 0.0, 1.0),
        _seg("doc_context", "DOC_CONTEXT", f"Document context says marker is {marker}. {_pad('mixdoc', 140)}", ["sys"], 0.0, 1.0),
    ]
    for t in range(2, turn + 1):
        segments.append(_seg(f"tool_obs_{t}", "TOOL_OBS", f"Dynamic tool observation {t} for mixed task.", ["sys"], 1.0, 0.0))
        if t % 2 == 0:
            segments.append(_seg(f"repo_function_{t}", "REPO_FUNCTION", f"FUNCTION SECTION {t}: follows repo_class. {_pad('mixfunc', 90)}", ["repo_class"], 0.0, 1.0))
    deps = ["repo_class", "doc_context", "tool_obs_1" if turn < 2 else f"tool_obs_{turn}"]
    if turn >= 2 and turn % 2 == 0:
        deps.append(f"repo_function_{turn}")
    segments.append(_seg("query", "USER_QUERY", f"Return marker {marker}; return ORDER_ERROR if repository order is broken.", deps, 0.1, 0.0))
    return {
        "trajectory_id": f"mixed_{i}",
        "turn_id": turn,
        "case_type": "mixed_agent",
        "expected_answer": marker,
        "unsafe_answer": "ORDER_ERROR",
        "tool_slack_ms": [0, 50, 100, 200, 500, 100][turn % 6],
        "segments": segments,
        "dependency_edges": _edges(segments),
    }


def build_multiturn_trajectories(trajectories_per_type: int = 2, turns: int = 6) -> list[dict[str, Any]]:
    rows = []
    for i in range(trajectories_per_type):
        for turn in range(turns):
            rows.append(_code_turn(i, turn))
            rows.append(_rag_turn(i, turn))
            rows.append(_mixed_turn(i, turn))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trajectories-per-type", type=int, default=2)
    parser.add_argument("--turns", type=int, default=6)
    parser.add_argument("--output", type=Path, default=Path("results/prefix_cache/phase12e_multiturn_trajectories_v0.jsonl"))
    args = parser.parse_args()
    rows = build_multiturn_trajectories(args.trajectories_per_type, args.turns)
    write_jsonl(args.output, rows)
    print(f"phase12e_trajectory_turns={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
