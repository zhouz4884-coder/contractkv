#!/usr/bin/env python3
"""Phase 12D Partial-Order Segment Contract layout compiler."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


STABLE_TYPES = {
    "SYS_PROMPT",
    "RAG_CHUNK",
    "SYNTHETIC_CONTEXT",
    "REPO_IMPORT",
    "REPO_CLASS",
    "REPO_FUNCTION",
    "REPO_CONTEXT",
    "DOC_CONTEXT",
}
VOLATILE_TYPES = {"TOOL_OBS", "SCRATCHPAD", "CHAT_HISTORY"}
QUERY_TYPES = {"USER_QUERY"}


def _segment_by_id(segments: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(segment["segment_id"]): segment for segment in segments}


def _deps(segment: dict[str, Any]) -> list[str]:
    return [str(item) for item in segment.get("dependencies", [])]


def _dependents(segments: list[dict[str, Any]]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for segment in segments:
        sid = str(segment["segment_id"])
        for dep in _deps(segment):
            out[dep].append(sid)
    return out


def validate_topological_order(order: list[str], segments: list[dict[str, Any]]) -> list[list[str]]:
    position = {sid: i for i, sid in enumerate(order)}
    violations: list[list[str]] = []
    for segment in segments:
        sid = str(segment["segment_id"])
        for dep in _deps(segment):
            if dep in position and sid in position and position[dep] > position[sid]:
                violations.append([dep, sid])
    return violations


def _score(segment: dict[str, Any]) -> float:
    token_count = float(segment.get("token_count") or 0)
    cache_stability = float(segment.get("cache_stability", 1.0 if segment.get("segment_type") in STABLE_TYPES else 0.0))
    reuse_probability = float(segment.get("reuse_probability", cache_stability))
    volatility = float(segment.get("volatility", 1.0 if segment.get("segment_type") in VOLATILE_TYPES else 0.0))
    boundary_risk = float(segment.get("boundary_risk", 0.0))
    query_penalty = 100000.0 if segment.get("segment_type") in QUERY_TYPES else 0.0
    sys_bonus = 1000000.0 if segment.get("segment_type") == "SYS_PROMPT" else 0.0
    return sys_bonus + token_count + 250.0 * cache_stability + 250.0 * reuse_probability - 500.0 * volatility - 1000.0 * boundary_risk - query_penalty


def prefix_max_topological_order(segments: list[dict[str, Any]]) -> list[str]:
    by_id = _segment_by_id(segments)
    remaining_deps = {sid: set(_deps(segment)) for sid, segment in by_id.items()}
    dependents = _dependents(segments)
    ready = {sid for sid, deps in remaining_deps.items() if not deps}
    order: list[str] = []
    while ready:
        sid = max(ready, key=lambda item: (_score(by_id[item]), -len(order), item))
        ready.remove(sid)
        order.append(sid)
        for child in dependents.get(sid, []):
            remaining_deps[child].discard(sid)
            if not remaining_deps[child]:
                ready.add(child)
    if len(order) != len(segments):
        missing = sorted(set(by_id) - set(order))
        raise ValueError(f"dependency cycle or missing dependency among segments: {missing}")
    return order


def canonical_all_order(segments: list[dict[str, Any]]) -> list[str]:
    def unsafe_score(segment: dict[str, Any]) -> tuple[float, str]:
        token_count = float(segment.get("token_count") or 0)
        volatility = float(segment.get("volatility", 1.0 if segment.get("segment_type") in VOLATILE_TYPES else 0.0))
        if segment.get("segment_type") == "SYS_PROMPT":
            token_count += 1000000.0
        if segment.get("segment_type") in QUERY_TYPES:
            token_count -= 1000000.0
        return (token_count - 1000.0 * volatility, str(segment["segment_id"]))

    return [str(segment["segment_id"]) for segment in sorted(segments, key=unsafe_score, reverse=True)]


def raw_order(segments: list[dict[str, Any]]) -> list[str]:
    return [str(segment["segment_id"]) for segment in segments]


def enumerate_legal_topological_orders(
    segments: list[dict[str, Any]],
    max_orders: int = 64,
) -> list[list[str]]:
    """Enumerate deterministic legal layouts, capped for larger prompt DAGs.

    Phase 14 uses this as a real legal-oracle candidate set.  The cap keeps
    independent RAG chunks from creating a factorial quality-scoring manifest.
    Known compiler layouts are added separately by the caller, so truncation
    here cannot silently remove the deployed candidate.
    """

    if max_orders <= 0:
        return []
    by_id = _segment_by_id(segments)
    dependents = _dependents(segments)
    remaining_deps = {sid: set(_deps(segment)) for sid, segment in by_id.items()}
    output: list[list[str]] = []

    def visit(order: list[str], deps: dict[str, set[str]]) -> None:
        if len(output) >= max_orders:
            return
        if len(order) == len(by_id):
            output.append(list(order))
            return
        ready = [sid for sid in by_id if sid not in order and not deps[sid]]
        ready.sort(key=lambda sid: (-_score(by_id[sid]), sid))
        for sid in ready:
            next_deps = {key: set(value) for key, value in deps.items()}
            for child in dependents.get(sid, []):
                next_deps[child].discard(sid)
            visit(order + [sid], next_deps)
            if len(output) >= max_orders:
                return

    visit([], remaining_deps)
    return output


def boolean_guard_order(segments: list[dict[str, Any]]) -> list[str]:
    if any(str(segment.get("segment_type", "")).startswith("REPO_") or segment.get("segment_type") == "REPO_CONTEXT" for segment in segments):
        return raw_order(segments)
    return prefix_max_topological_order(segments)


def add_structural_anchors(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    anchored = []
    for segment in segments:
        copy = dict(segment)
        sid = str(segment["segment_id"])
        stype = str(segment.get("segment_type", "UNKNOWN"))
        copy["text"] = f'\n\n[SEGMENT type="{stype}" id="{sid}"]\n{segment.get("text", "")}\n[/SEGMENT]\n'
        copy["structural_anchor_tokens_added"] = 6
        copy["token_count"] = int(segment.get("token_count") or 0) + 6
        anchored.append(copy)
    return anchored


def expected_prefix_gain_tokens(order: list[str], segments: list[dict[str, Any]]) -> int:
    by_id = _segment_by_id(segments)
    total = 0
    for sid in order:
        segment = by_id[sid]
        stype = segment.get("segment_type")
        volatility = float(segment.get("volatility", 1.0 if stype in VOLATILE_TYPES else 0.0))
        if stype in QUERY_TYPES or volatility >= 0.5:
            break
        total += int(segment.get("token_count") or 0)
    return total


def _layout_decision(order: list[str], segments: list[dict[str, Any]]) -> str:
    raw = raw_order(segments)
    if order == raw:
        return "raw_order"
    raw_positions = {sid: i for i, sid in enumerate(raw)}
    moved = [sid for i, sid in enumerate(order) if raw_positions.get(sid) != i]
    return "partial_canonical" if moved else "raw_order"


def _ordered_text(order: list[str], segments: list[dict[str, Any]]) -> str:
    by_id = _segment_by_id(segments)
    return "\n\n".join(f"[{by_id[sid].get('segment_type')}:{sid}]\n{by_id[sid].get('text', '')}" for sid in order)


def compile_layout(segments: list[dict[str, Any]], policy: str = "posc", structural_anchors: bool = False) -> dict[str, Any]:
    working = add_structural_anchors(segments) if structural_anchors else [dict(segment) for segment in segments]
    if policy == "raw-order":
        order = raw_order(working)
    elif policy == "canonical-all":
        order = canonical_all_order(working)
    elif policy == "boolean-guarded":
        order = boolean_guard_order(working)
    elif policy in {"posc", "posc-anchors"}:
        order = prefix_max_topological_order(working)
    else:
        raise ValueError(f"unknown policy: {policy}")
    violations = validate_topological_order(order, working)
    decision = _layout_decision(order, working)
    if policy == "canonical-all" and violations:
        decision = "unsafe_canonical"
    if policy == "posc-anchors":
        decision = "partial_canonical_anchored" if decision != "raw_order" else "raw_order_anchored"
    raw_prefix = expected_prefix_gain_tokens(raw_order(working), working)
    compiled_prefix = expected_prefix_gain_tokens(order, working)
    return {
        "policy": policy,
        "layout_decision": decision,
        "topological_order": order,
        "dependency_edges": [[dep, str(segment["segment_id"])] for segment in working for dep in _deps(segment)],
        "violated_edges": violations,
        "canonicalized_tokens": max(0, compiled_prefix - raw_prefix),
        "raw_order_preserved_tokens": raw_prefix if decision == "raw_order" else 0,
        "expected_prefix_gain_tokens": compiled_prefix,
        "structural_anchor_tokens_added": sum(int(segment.get("structural_anchor_tokens_added") or 0) for segment in working),
        "compiled_text": _ordered_text(order, working),
        "reason": "prefix_maximizing_topological_sort" if not violations else "unsafe_dependency_violation",
    }


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("results/prefix_cache/phase12d_posc_layout_decisions_v0.jsonl"))
    parser.add_argument("--policies", default="raw-order,canonical-all,boolean-guarded,posc,posc-anchors")
    args = parser.parse_args()
    rows = []
    for case in load_jsonl(args.cases):
        for policy in [item.strip() for item in args.policies.split(",") if item.strip()]:
            result = compile_layout(case["segments"], policy=policy, structural_anchors=(policy == "posc-anchors"))
            result.update({"trace_id": case["trace_id"], "case_type": case.get("case_type", ""), "expected_answer": case.get("expected_answer", "")})
            result.pop("compiled_text", None)
            rows.append(result)
    write_jsonl(args.output, rows)
    print(f"layout_decisions={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
