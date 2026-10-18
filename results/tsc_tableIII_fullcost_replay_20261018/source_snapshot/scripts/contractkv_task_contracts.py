#!/usr/bin/env python3
"""Conservative deterministic output contracts for online Tier-2 admission."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import asdict, dataclass


CONTRACT_VERSION = "phase20.deterministic-contracts.v4"


@dataclass(frozen=True)
class ContractResult:
    supported: bool
    equivalent: bool
    contract_type: str
    contract_version: str
    raw_canonical_hash: str
    candidate_canonical_hash: str
    failure_reason: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def strip_reasoning(value: str) -> str:
    value = re.sub(r"<think>.*?</think>", "", value, flags=re.I | re.S)
    value = value.strip()
    fenced = re.fullmatch(r"```(?:python)?\s*(.*?)\s*```", value, flags=re.I | re.S)
    return fenced.group(1).strip() if fenced else value


def strip_leading_control_echo(value: str) -> str:
    """Remove only a leading, self-contained control-directive echo."""
    value = strip_reasoning(value)
    while True:
        match = re.match(r"^\s*\[[^\]\n]{8,512}\]\s*(?:\n+|$)", value)
        if not match:
            return value.strip()
        value = value[match.end():]


def normalize_answer(value: str) -> str:
    value = strip_leading_control_echo(value)
    match = re.search(r"(?:^|\n)\s*(?:final answer|answer)\s*:\s*(.+?)\s*$",
                      value, flags=re.I | re.S)
    if match:
        value = match.group(1)
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if len(lines) > 1:
        value = lines[-1]
    value = value.lower()
    value = re.sub(r"[^\w\s-]", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def normalize_code(value: str) -> str:
    value = strip_reasoning(value).replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in value.split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def _result(contract_type: str, raw: str, candidate: str,
            equivalent: bool, failure: str = "") -> ContractResult:
    return ContractResult(
        supported=True, equivalent=equivalent, contract_type=contract_type,
        contract_version=CONTRACT_VERSION,
        raw_canonical_hash=digest_text(raw),
        candidate_canonical_hash=digest_text(candidate),
        failure_reason=failure,
    )


def evaluate_contract(dataset: str, task: str, raw_output: str,
                      candidate_output: str) -> ContractResult:
    if dataset == "RULER":
        raw = normalize_answer(raw_output)
        candidate = normalize_answer(candidate_output)
        return _result("ruler_normalized_final_exact", raw, candidate,
                       bool(raw) and raw == candidate,
                       "empty_or_different_final_answer" if not raw or raw != candidate else "")

    if dataset == "LongBench" and task in {"hotpotqa", "qasper", "narrativeqa"}:
        raw = normalize_answer(raw_output)
        candidate = normalize_answer(candidate_output)
        equivalent = bool(raw) and raw == candidate
        return _result("longbench_terminal_exact", raw, candidate, equivalent,
                       "empty_or_different_final_answer" if not equivalent else "")

    if dataset == "RepoBench":
        raw_code = normalize_code(raw_output)
        candidate_code = normalize_code(candidate_output)
        try:
            raw_ast = ast.dump(ast.parse(raw_code), include_attributes=False)
            candidate_ast = ast.dump(ast.parse(candidate_code), include_attributes=False)
        except SyntaxError:
            return _result("repobench_normalized_exact_fragment", raw_code,
                           candidate_code, bool(raw_code) and raw_code == candidate_code,
                           "fragment_exact_mismatch" if not raw_code or raw_code != candidate_code else "")
        return _result("repobench_python_ast_exact", raw_ast, candidate_ast,
                       raw_ast == candidate_ast,
                       "ast_mismatch" if raw_ast != candidate_ast else "")

    empty = digest_text("")
    return ContractResult(False, False, "unsupported", CONTRACT_VERSION,
                          empty, empty, "unsupported_task_contract")


def contract_manifest_hash() -> str:
    payload = {
        "version": CONTRACT_VERSION,
        "rules": [
            "RULER:normalized-final-exact",
            "LongBench/hotpotqa,qasper,narrativeqa:terminal-field-exact",
            "RepoBench:AST-exact-or-normalized-fragment-exact",
        ],
        "ground_truth_allowed": False,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
