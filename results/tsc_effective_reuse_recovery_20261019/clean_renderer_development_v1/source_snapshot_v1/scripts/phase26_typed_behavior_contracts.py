#!/usr/bin/env python3
"""Deterministic, fail-closed typed behavioral contracts for Phase 26."""

from __future__ import annotations

import ast
from collections import Counter
import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass
from typing import Any


CONTRACT_VERSION = "phase26.typed-behavior.v1"


@dataclass(frozen=True)
class TypedContractResult:
    decision: str
    contract_type: str
    contract_version: str
    raw_canonical_hash: str
    candidate_canonical_hash: str
    failure_reason: str
    runtime_ms: float
    ground_truth_used: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _strip_reasoning(value: str) -> str:
    value = re.sub(r"<think>.*?</think>", "", value, flags=re.I | re.S).strip()
    fenced = re.fullmatch(r"```(?:python)?\s*(.*?)\s*```", value, flags=re.I | re.S)
    return fenced.group(1).strip() if fenced else value


def normalize_answer(value: str) -> str:
    value = _strip_reasoning(value)
    match = re.search(r"(?:^|\n)\s*(?:final answer|answer)\s*:\s*(.+?)\s*$", value,
                      flags=re.I | re.S)
    if match:
        value = match.group(1)
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if len(lines) > 1:
        value = lines[-1]
    value = re.sub(r"[^\w\s.\-]", " ", value.lower(), flags=re.UNICODE)
    return " ".join(value.split())


def _token_f1(left: str, right: str) -> float:
    a = normalize_answer(left).split(); b = normalize_answer(right).split()
    if not a or not b:
        return float(a == b)
    overlap = sum((Counter(a) & Counter(b)).values())
    if not overlap:
        return 0.0
    precision = overlap / len(b); recall = overlap / len(a)
    return 2 * precision * recall / (precision + recall)


def _bounded_qa_guards(raw: str, candidate: str) -> tuple[bool, str]:
    numbers = lambda value: re.findall(r"[-+]?\d+(?:\.\d+)?", value)
    polarity = lambda value: set(re.findall(
        r"\b(?:not|no|never|without|cannot|false|true)\b", value.lower()))
    if numbers(raw) != numbers(candidate):
        return False, "numeric_field_mismatch"
    if polarity(raw) != polarity(candidate):
        return False, "polarity_marker_mismatch"
    raw_words = max(1, len(normalize_answer(raw).split()))
    candidate_words = max(1, len(normalize_answer(candidate).split()))
    if max(raw_words, candidate_words) / min(raw_words, candidate_words) > 2.0:
        return False, "answer_length_ratio_exceeds_2"
    return True, ""


def _result(kind: str, raw: str, candidate: str, decision: str,
            reason: str, started: float) -> TypedContractResult:
    return TypedContractResult(
        decision=decision, contract_type=kind, contract_version=CONTRACT_VERSION,
        raw_canonical_hash=_hash(raw), candidate_canonical_hash=_hash(candidate),
        failure_reason=reason, runtime_ms=(time.perf_counter() - started) * 1000.0,
    )


def evaluate_typed_contract(dataset: str, task: str, raw_output: str,
                            candidate_output: str,
                            context_text: str = "",
                            qa_f1_threshold: float | None = None) -> TypedContractResult:
    """Evaluate without references; UNKNOWN always means fail closed online."""
    started = time.perf_counter()
    raw = normalize_answer(raw_output)
    candidate = normalize_answer(candidate_output)
    if dataset == "RULER":
        equivalent = bool(raw) and raw == candidate
        return _result("ruler_normalized_exact", raw, candidate,
                       "PASS" if equivalent else "FAIL",
                       "" if equivalent else "normalized_answer_mismatch", started)

    if dataset == "LongBench" and task in {"hotpotqa", "qasper", "narrativeqa"}:
        equivalent = bool(raw) and raw == candidate
        if not equivalent and qa_f1_threshold is not None:
            guards, reason = _bounded_qa_guards(raw_output, candidate_output)
            score = _token_f1(raw_output, candidate_output)
            bounded = guards and score >= qa_f1_threshold
            return _result("qa_bounded_lexical_v1", raw, candidate,
                           "PASS" if bounded else "FAIL",
                           "" if bounded else (reason or f"token_f1_below_{qa_f1_threshold}"), started)
        return _result("qa_normalized_span_exact", raw, candidate,
                       "PASS" if equivalent else "UNKNOWN",
                       "" if equivalent else "different_free_form_answer_fail_closed", started)

    if dataset == "RepoBench":
        raw_code = _strip_reasoning(raw_output).replace("\r\n", "\n").strip()
        candidate_code = _strip_reasoning(candidate_output).replace("\r\n", "\n").strip()
        if raw_code == candidate_code and raw_code:
            return _result("code_fragment_exact", raw_code, candidate_code, "PASS", "", started)
        try:
            raw_ast = ast.dump(ast.parse(raw_code), include_attributes=False)
            candidate_ast = ast.dump(ast.parse(candidate_code), include_attributes=False)
        except SyntaxError:
            # Completion fragments often cannot parse alone. Reinsert only when
            # the supplied context itself forms a deterministic Python prefix.
            if context_text:
                try:
                    raw_ast = ast.dump(ast.parse(context_text + raw_code), include_attributes=False)
                    candidate_ast = ast.dump(ast.parse(context_text + candidate_code), include_attributes=False)
                except SyntaxError:
                    return _result("code_structural", raw_code, candidate_code, "UNKNOWN",
                                   "fragment_or_reinserted_program_not_parseable", started)
            else:
                return _result("code_structural", raw_code, candidate_code, "UNKNOWN",
                               "missing_parseable_context", started)
        equivalent = raw_ast == candidate_ast
        return _result("code_ast_exact", raw_ast, candidate_ast,
                       "PASS" if equivalent else "FAIL",
                       "" if equivalent else "ast_mismatch", started)

    return _result("strict_only", raw, candidate, "UNKNOWN",
                   "unsupported_workflow", started)


def contract_manifest() -> dict[str, Any]:
    payload = {
        "version": CONTRACT_VERSION,
        "ground_truth_allowed": False,
        "rules": [
            "RULER:normalized-answer-exact",
            "LongBench:normalized-free-form-exact-else-unknown",
            "LongBench/bounded:token-F1-threshold+numeric+polarity+length-ratio",
            "RepoBench:fragment-exact-or-AST-exact-else-fail-closed",
            "unsupported:strict-only",
        ],
        "required_context": {
            "RepoBench": "raw repository prefix when syntactically composable",
        },
    }
    payload["code_hash"] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return payload
