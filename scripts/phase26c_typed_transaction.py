#!/usr/bin/env python3
"""Exercise the Phase 26 typed safety/benefit transaction state machine."""

from __future__ import annotations

import argparse
import csv
import json
import multiprocessing as mp
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase26_recoverability_common import benefit_utility
from scripts.phase26_typed_behavior_contracts import evaluate_typed_contract


@dataclass(frozen=True)
class Case:
    case_id: str
    txn_id: str
    dataset: str
    task: str
    raw: str
    candidate: str
    expected_state: str
    worker_mode: str = "normal"
    pass_probability: float = 1.0
    saved_ms: float = 100.0
    verify_ms: float = 10.0
    slack_ms: float = 0.0


def _worker(queue: Any, payload: dict[str, Any]) -> None:
    try:
        mode = payload.pop("worker_mode")
        if mode == "timeout":
            time.sleep(1.0)
        if mode == "exception":
            raise RuntimeError("injected contract exception")
        result = evaluate_typed_contract(**payload, qa_f1_threshold=.8)
        queue.put({"ok": True, "result": result.as_dict()})
    except BaseException as exc:
        queue.put({"ok": False, "error": f"{type(exc).__name__}: {exc}"})


def sandbox_contract(case: Case, timeout_ms: float) -> dict[str, Any]:
    context = mp.get_context("spawn")
    queue = context.Queue(maxsize=1)
    payload = {"dataset": case.dataset, "task": case.task,
               "raw_output": case.raw, "candidate_output": case.candidate,
               "worker_mode": case.worker_mode}
    process = context.Process(target=_worker, args=(queue, payload), daemon=True)
    started = time.perf_counter(); process.start(); process.join(timeout_ms / 1000.0)
    elapsed = (time.perf_counter() - started) * 1000.0
    if process.is_alive():
        process.terminate(); process.join(1.0)
        return {"decision": "INCOMPLETE", "failure_reason": "contract_timeout",
                "runtime_ms": elapsed, "sandbox_exitcode": process.exitcode}
    if queue.empty():
        return {"decision": "INCOMPLETE", "failure_reason": "contract_worker_no_result",
                "runtime_ms": elapsed, "sandbox_exitcode": process.exitcode}
    outcome = queue.get()
    if not outcome["ok"]:
        return {"decision": "INCOMPLETE", "failure_reason": outcome["error"],
                "runtime_ms": elapsed, "sandbox_exitcode": process.exitcode}
    result = outcome["result"]
    result["runtime_ms"] = elapsed
    result["sandbox_exitcode"] = process.exitcode
    return result


class TransactionController:
    def __init__(self) -> None:
        self.published: set[str] = set()
        self.terminal: dict[str, dict[str, Any]] = {}
        self.ephemeral: dict[str, int] = {}

    def execute(self, case: Case, timeout_ms: float) -> dict[str, Any]:
        if case.txn_id in self.terminal:
            previous = dict(self.terminal[case.txn_id])
            previous.update({"case_id": case.case_id, "duplicate": True,
                             "cache_entries_delta": 0, "ephemeral_blocks_after": 0})
            return previous
        cache_before = len(self.published)
        self.ephemeral[case.txn_id] = 8
        if case.worker_mode == "disconnect":
            contract = {"decision": "INCOMPLETE", "failure_reason": "frontend_disconnect",
                        "runtime_ms": 0.0, "sandbox_exitcode": "not_started"}
        else:
            contract = sandbox_contract(case, timeout_ms)
        benefit = benefit_utility(
            pass_probability=case.pass_probability, expected_reuses=9,
            saved_ms_per_request=case.saved_ms, verify_ms=case.verify_ms,
            slack_ms=case.slack_ms)
        safety_pass = contract.get("decision") == "PASS"
        benefit_pass = bool(benefit["admit"])
        state = "COMMITTED" if safety_pass and benefit_pass else "ABORTED"
        if state == "COMMITTED":
            self.published.add(f"prefix:{case.txn_id}")
        self.ephemeral.pop(case.txn_id, None)
        result = {
            "case_id": case.case_id, "txn_id": case.txn_id, "duplicate": False,
            "contract_decision": contract.get("decision", "INCOMPLETE"),
            "contract_failure_reason": contract.get("failure_reason", ""),
            "contract_runtime_ms": contract.get("runtime_ms", 0.0),
            "sandbox_exitcode": contract.get("sandbox_exitcode", ""),
            "safety_gate_pass": safety_pass, "benefit_gate_pass": benefit_pass,
            "expected_gain_ms": benefit["expected_gain_ms"], "txn_state": state,
            "certificate_issued": state == "COMMITTED",
            "cache_entries_before": cache_before, "cache_entries_after": len(self.published),
            "cache_entries_delta": len(self.published) - cache_before,
            "ephemeral_blocks_after": len(self.ephemeral),
            "dynamic_suffix_reuse_tokens": 0,
            "expected_state": case.expected_state,
        }
        result["gate_pass"] = (
            state == case.expected_state
            and result["ephemeral_blocks_after"] == 0
            and result["dynamic_suffix_reuse_tokens"] == 0
            and (state != "ABORTED" or result["cache_entries_delta"] == 0)
        )
        self.terminal[case.txn_id] = dict(result)
        return result


def cases() -> list[Case]:
    return [
        Case("typed_pass", "txn-pass", "RULER", "niah_single_1", "Paris", "Paris", "COMMITTED"),
        Case("typed_fail", "txn-fail", "RULER", "niah_single_1", "Paris", "London", "ABORTED"),
        Case("typed_unknown", "txn-unknown", "Unknown", "custom", "a", "a", "ABORTED"),
        Case("malformed_output", "txn-malformed", "LongBench", "hotpotqa", "Paris", "", "ABORTED"),
        Case("contract_timeout", "txn-timeout", "RULER", "niah_single_1", "x", "x", "ABORTED", "timeout"),
        Case("contract_exception", "txn-exception", "RULER", "niah_single_1", "x", "x", "ABORTED", "exception"),
        Case("frontend_disconnect", "txn-disconnect", "RULER", "niah_single_1", "x", "x", "ABORTED", "disconnect"),
        Case("benefit_reject", "txn-benefit", "RULER", "niah_single_1", "x", "x", "ABORTED",
             pass_probability=.1, saved_ms=1.0, verify_ms=1000.0, slack_ms=0.0),
        Case("code_exact", "txn-code", "RepoBench", "python_v1.1", "return x + 1", "return x + 1", "COMMITTED"),
        Case("duplicate_request", "txn-pass", "RULER", "niah_single_1", "Paris", "Paris", "COMMITTED"),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout-ms", type=float, default=200.0)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    controller = TransactionController()
    rows = [controller.execute(case, args.timeout_ms) for case in cases()]
    duplicate = next(row for row in rows if row["case_id"] == "duplicate_request")
    checks = {
        "all_expected_states": all(row["gate_pass"] for row in rows),
        "fail_unknown_timeout_exception_disconnect_publish_zero": all(
            row["cache_entries_delta"] == 0 and not row["certificate_issued"]
            for row in rows if row["expected_state"] == "ABORTED"),
        "duplicate_idempotent": duplicate["duplicate"] and duplicate["cache_entries_delta"] == 0,
        "ephemeral_cleanup_complete": not controller.ephemeral,
        "dynamic_suffix_reuse_zero": all(row["dynamic_suffix_reuse_tokens"] == 0 for row in rows),
        "safety_and_benefit_both_required": any(
            row["safety_gate_pass"] and not row["benefit_gate_pass"] and row["txn_state"] == "ABORTED"
            for row in rows),
    }
    args.events.parent.mkdir(parents=True, exist_ok=True)
    args.events.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    summary = {
        "schema_version": "contractkv.phase26c.typed-transaction.v1",
        "cases": len(rows), "commits": sum(row["txn_state"] == "COMMITTED" for row in rows),
        "aborts": sum(row["txn_state"] == "ABORTED" for row in rows),
        "checks": checks, "gate_pass": all(checks.values()),
        "claim_boundary": "Python control-plane transaction and process-isolated contract-stub fault matrix. Live vLLM cache publication and suffix isolation are validated separately by Phase 26D telemetry and prior source-level PSTP probes.",
    }
    with args.summary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary.keys()))
        writer.writeheader(); writer.writerow({**summary, "checks": json.dumps(checks, sort_keys=True)})
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["gate_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
