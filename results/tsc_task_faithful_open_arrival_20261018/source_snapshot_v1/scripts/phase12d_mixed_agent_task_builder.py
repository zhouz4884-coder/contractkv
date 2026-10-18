#!/usr/bin/env python3
"""Build Phase 12D mixed-agent cases with partial-order segment contracts."""

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
    return [[dep, segment["segment_id"]] for segment in segments for dep in segment.get("dependencies", [])]


def _code_tool_case(i: int) -> dict[str, Any]:
    marker = f"MIXED_CODE_{i}"
    segments = [
        _seg("sys", "SYS_PROMPT", "If repository sections are not ordered IMPORT before CLASS before FUNCTION, answer ORDER_ERROR. Otherwise return the marker value stated in FUNCTION SECTION only. Do not return the literal function name. /no_think", [], 0.0, 1.0),
        _seg("tool", "TOOL_OBS", f"Dynamic tool observation {i}: build status is green. This observation does not define repository symbols.", ["sys"], 1.0, 0.0),
        _seg("repo_import", "REPO_IMPORT", f"IMPORT SECTION: BASE_TOKEN_{i} is imported from contractkv.runtime.base.", ["sys"], 0.0, 1.0),
        _seg("repo_class", "REPO_CLASS", f"CLASS SECTION: ContractKVPlanner_{i} extends BASE_TOKEN_{i} and exposes CLASS_TOKEN_{i}.", ["repo_import"], 0.0, 1.0),
        _seg("repo_function", "REPO_FUNCTION", f"FUNCTION SECTION: final_marker() combines BASE_TOKEN_{i} then CLASS_TOKEN_{i} and returns {marker}.", ["repo_class"], 0.0, 1.0),
        _seg("query", "USER_QUERY", "Return the marker value produced by final_marker(). Do not output the literal string final_marker(). If dependency order is broken, return ORDER_ERROR.", ["tool", "repo_function"], 0.1, 0.0),
    ]
    return {
        "trace_id": f"mixed_code_tool_{i}",
        "case_type": "code_tool",
        "expected_answer": marker,
        "unsafe_answer": "ORDER_ERROR",
        "segments": segments,
        "dependency_edges": _edges(segments),
    }


def _rag_tool_case(i: int) -> dict[str, Any]:
    marker = f"MIXED_RAG_{i}"
    segments = [
        _seg("sys", "SYS_PROMPT", "Answer with only the requested marker from the stable documents. /no_think", [], 0.0, 1.0),
        _seg("tool", "TOOL_OBS", f"Dynamic tool observation {i}: no additional evidence.", ["sys"], 1.0, 0.0),
        _seg("doc_a", "RAG_CHUNK", f"Stable document A says the ContractKV marker is {marker}.", ["sys"], 0.0, 1.0),
        _seg("doc_b", "RAG_CHUNK", "Stable document B explains that independent RAG chunks can be reordered before volatile tool observations.", ["sys"], 0.0, 1.0),
        _seg("query", "USER_QUERY", "Return the ContractKV marker only.", ["tool", "doc_a", "doc_b"], 0.1, 0.0),
    ]
    return {
        "trace_id": f"mixed_rag_tool_{i}",
        "case_type": "rag_tool",
        "expected_answer": marker,
        "unsafe_answer": "ORDER_ERROR",
        "segments": segments,
        "dependency_edges": _edges(segments),
    }


def _repo_doc_tool_case(i: int) -> dict[str, Any]:
    marker = f"MIXED_REPODOC_{i}"
    segments = [
        _seg("sys", "SYS_PROMPT", "Keep repository dependency order intact. Answer with the marker only unless repository order is broken. /no_think", [], 0.0, 1.0),
        _seg("tool", "TOOL_OBS", f"Dynamic tool observation {i}: user asked for a repository-grounded answer.", ["sys"], 1.0, 0.0),
        _seg("repo_import", "REPO_IMPORT", f"IMPORT SECTION: repo module defines DOC_BASE_{i}.", ["sys"], 0.0, 1.0),
        _seg("repo_class", "REPO_CLASS", f"CLASS SECTION: doc planner uses DOC_BASE_{i}.", ["repo_import"], 0.0, 1.0),
        _seg("doc_context", "DOC_CONTEXT", f"Document context confirms the requested marker is {marker}.", ["sys"], 0.0, 1.0),
        _seg("query", "USER_QUERY", "Return the requested marker. If repository order is broken, return ORDER_ERROR.", ["tool", "repo_class", "doc_context"], 0.1, 0.0),
    ]
    return {
        "trace_id": f"mixed_repo_doc_tool_{i}",
        "case_type": "repo_doc_tool",
        "expected_answer": marker,
        "unsafe_answer": "ORDER_ERROR",
        "segments": segments,
        "dependency_edges": _edges(segments),
    }


def build_mixed_agent_cases(cases_per_type: int = 10) -> list[dict[str, Any]]:
    cases = []
    for i in range(cases_per_type):
        cases.append(_code_tool_case(i))
        cases.append(_rag_tool_case(i))
        cases.append(_repo_doc_tool_case(i))
    return cases


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases-per-type", type=int, default=10)
    parser.add_argument("--output", type=Path, default=Path("results/prefix_cache/phase12d_mixed_agent_cases_v0.jsonl"))
    args = parser.parse_args()
    rows = build_mixed_agent_cases(args.cases_per_type)
    write_jsonl(args.output, rows)
    print(f"mixed_agent_cases={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
