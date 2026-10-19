#!/usr/bin/env python3
"""Fail-closed deterministic contracts for observation-scoped Phase 26R."""

from __future__ import annotations

import ast
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Any


CONTRACT_VERSION = "phase26r.typed-behavior.v2"


def _source_hash() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _strip_reasoning(value: str) -> str:
    value = re.sub(r"<think>.*?</think>", "", value, flags=re.I | re.S).strip()
    fenced = re.fullmatch(r"```(?:python)?\s*(.*?)\s*```", value, flags=re.I | re.S)
    return fenced.group(1).strip() if fenced else value


def normalize_full_answer(value: str) -> str:
    """Normalize the complete answer; never silently keep only its last line."""
    value = _strip_reasoning(value)
    match = re.fullmatch(r"\s*(?:final answer|answer)\s*:\s*(.*?)\s*", value,
                         flags=re.I | re.S)
    if match:
        value = match.group(1)
    value = re.sub(r"[^\w\s.\-]", " ", value.lower(), flags=re.UNICODE)
    return " ".join(value.split())


def diagnostic_token_f1(left: str, right: str) -> float:
    from collections import Counter

    a = normalize_full_answer(left).split()
    b = normalize_full_answer(right).split()
    if not a or not b:
        return float(a == b)
    overlap = sum((Counter(a) & Counter(b)).values())
    if not overlap:
        return 0.0
    precision = overlap / len(b)
    recall = overlap / len(a)
    return 2 * precision * recall / (precision + recall)


def repository_context_text(case: dict[str, Any]) -> str:
    """Return exactly the code-bearing prefix used by audit, freeze and live."""
    return "\n".join(
        str(segment.get("text", ""))
        for segment in case.get("segments", [])
        if str(segment.get("segment_type", ""))
        not in {"SYS_PROMPT", "TOOL_OBS", "USER_QUERY"}
    )


@dataclass(frozen=True)
class ContractResult:
    decision: str
    contract_type: str
    contract_version: str
    contract_code_hash: str
    raw_canonical_hash: str
    candidate_canonical_hash: str
    failure_reason: str
    runtime_ms: float
    lexical_f1_diagnostic: float
    ground_truth_used: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _result(kind: str, raw: str, candidate: str, decision: str,
            reason: str, started: float, lexical_f1: float) -> ContractResult:
    return ContractResult(
        decision=decision,
        contract_type=kind,
        contract_version=CONTRACT_VERSION,
        contract_code_hash=_source_hash(),
        raw_canonical_hash=_hash(raw),
        candidate_canonical_hash=_hash(candidate),
        failure_reason=reason,
        runtime_ms=(time.perf_counter() - started) * 1000.0,
        lexical_f1_diagnostic=lexical_f1,
    )


def evaluate_typed_contract(dataset: str, task: str, raw_output: str,
                            candidate_output: str, context_text: str = "") -> ContractResult:
    """Evaluate a reference-free deterministic contract for one observation.

    Open-ended QA lexical similarity is diagnostic-only. UNKNOWN is a mandatory
    online fallback and cannot publish candidate cache state.
    """
    started = time.perf_counter()
    raw = normalize_full_answer(raw_output)
    candidate = normalize_full_answer(candidate_output)
    lexical_f1 = diagnostic_token_f1(raw_output, candidate_output)

    if dataset == "RULER":
        same = bool(raw) and raw == candidate
        return _result("ruler_normalized_exact_v2", raw, candidate,
                       "PASS" if same else "FAIL",
                       "" if same else "normalized_answer_mismatch", started, lexical_f1)

    if dataset == "LongBench" and task in {"hotpotqa", "qasper", "narrativeqa"}:
        same = bool(raw) and raw == candidate
        return _result("open_qa_exact_or_unknown_v2", raw, candidate,
                       "PASS" if same else "UNKNOWN",
                       "" if same else "lexical_f1_is_diagnostic_only", started, lexical_f1)

    if dataset == "RepoBench":
        raw_code = _strip_reasoning(raw_output).replace("\r\n", "\n").strip()
        candidate_code = _strip_reasoning(candidate_output).replace("\r\n", "\n").strip()
        if raw_code and raw_code == candidate_code:
            return _result("code_fragment_exact_v2", raw_code, candidate_code,
                           "PASS", "", started, lexical_f1)
        variants = [(raw_code, candidate_code, "fragment")]
        if context_text:
            variants.append((context_text + raw_code, context_text + candidate_code,
                             "repository_context"))
        for raw_program, candidate_program, source in variants:
            try:
                raw_ast = ast.dump(ast.parse(raw_program), include_attributes=False)
                candidate_ast = ast.dump(ast.parse(candidate_program), include_attributes=False)
            except SyntaxError:
                continue
            same = raw_ast == candidate_ast
            return _result(f"code_ast_exact_v2:{source}", raw_ast, candidate_ast,
                           "PASS" if same else "FAIL",
                           "" if same else "ast_mismatch", started, lexical_f1)
        return _result("code_ast_exact_v2", raw_code, candidate_code, "UNKNOWN",
                       "fragment_or_reinserted_program_not_parseable", started, lexical_f1)

    return _result("strict_only_v2", raw, candidate, "UNKNOWN",
                   "unsupported_workflow", started, lexical_f1)


def contract_manifest() -> dict[str, Any]:
    payload = {
        "version": CONTRACT_VERSION,
        "contract_code_hash": _source_hash(),
        "certificate_scope": "one observation identity and epoch",
        "ground_truth_allowed_online": False,
        "lexical_f1_role": "routing_and_diagnostic_only_never_PASS",
        "rules": {
            "RULER": "normalized complete-answer exact",
            "LongBench": "normalized complete-answer exact else UNKNOWN",
            "RepoBench": "fragment exact or AST exact with frozen repository context",
            "unsupported": "UNKNOWN",
        },
        "unknown_action": "abort_and_raw_fallback",
    }
    payload["manifest_hash"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return payload
