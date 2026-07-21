#!/usr/bin/env python3
"""Randomized concurrency stress for the explicit PSTP publication state machine.

This is a deterministic control-plane test, complementary to the smaller live
vLLM source-hook fault probes.  It exercises transaction interleavings and
asserts that publication is an all-or-nothing exact-LCP operation.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable


class State(str, Enum):
    PRIVATE = "PRIVATE"
    VERIFYING = "VERIFYING"
    VERIFIED = "VERIFIED"
    COMMITTED = "COMMITTED"
    ABORTED = "ABORTED"


@dataclass
class Transaction:
    txn_id: str
    exact_lcp_blocks: tuple[int, ...]
    scope: str
    epoch: int
    state: State = State.PRIVATE
    published_blocks: tuple[int, ...] = ()
    certificate_epoch: int | None = None
    terminal: bool = False
    history: list[str] = field(default_factory=lambda: [State.PRIVATE.value])


class PSTPStateMachine:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._transactions: dict[str, Transaction] = {}
        self._committed: dict[str, Transaction] = {}
        self._violations: list[str] = []

    def open(self, txn: Transaction) -> None:
        with self._lock:
            if txn.txn_id in self._transactions:
                self._violations.append(f"duplicate_open:{txn.txn_id}")
                return
            self._transactions[txn.txn_id] = txn

    def apply(self, txn_id: str, action: str, *, scope: str, epoch: int) -> None:
        with self._lock:
            txn = self._transactions[txn_id]
            if txn.terminal:
                # Idempotent duplicate delivery is legal only after a terminal state.
                if action not in {"duplicate", "restart"}:
                    self._violations.append(f"post_terminal:{txn_id}:{action}")
                return
            if action == "begin_verify":
                if txn.state is not State.PRIVATE:
                    self._violations.append(f"invalid_begin:{txn_id}:{txn.state}")
                    return
                txn.state = State.VERIFYING; txn.history.append(txn.state.value)
            elif action == "verify_pass":
                if txn.state is not State.VERIFYING:
                    self._violations.append(f"invalid_pass:{txn_id}:{txn.state}")
                    return
                if scope != txn.scope or epoch != txn.epoch:
                    txn.state = State.ABORTED; txn.terminal = True
                else:
                    txn.state = State.VERIFIED
                txn.history.append(txn.state.value)
            elif action in {"verify_fail", "timeout", "scope_mismatch", "invalidation", "eviction", "restart"}:
                txn.state = State.ABORTED; txn.terminal = True; txn.history.append(txn.state.value)
            elif action == "commit":
                if txn.state is not State.VERIFIED:
                    self._violations.append(f"invalid_commit:{txn_id}:{txn.state}")
                    return
                if scope != txn.scope or epoch != txn.epoch:
                    txn.state = State.ABORTED; txn.terminal = True; txn.history.append(txn.state.value)
                    return
                txn.published_blocks = txn.exact_lcp_blocks
                txn.certificate_epoch = epoch
                txn.state = State.COMMITTED; txn.terminal = True; txn.history.append(txn.state.value)
                self._committed[txn.txn_id] = txn
            elif action == "duplicate":
                # Replayed messages cannot advance state or publish extra blocks.
                txn.history.append("DUPLICATE")
            else:
                self._violations.append(f"unknown_action:{action}")

    def audit(self) -> list[str]:
        with self._lock:
            failures = list(self._violations)
            for txn in self._transactions.values():
                if txn.state is State.COMMITTED:
                    if txn.published_blocks != txn.exact_lcp_blocks:
                        failures.append(f"non_exact_publication:{txn.txn_id}")
                    if not txn.published_blocks:
                        failures.append(f"empty_commit:{txn.txn_id}")
                    if txn.certificate_epoch != txn.epoch:
                        failures.append(f"stale_certificate:{txn.txn_id}")
                elif txn.published_blocks:
                    failures.append(f"suffix_or_abort_publication:{txn.txn_id}")
                if txn.history[0] != State.PRIVATE.value:
                    failures.append(f"non_private_start:{txn.txn_id}")
            return failures

    @property
    def transactions(self) -> Iterable[Transaction]:
        return self._transactions.values()


def sequence(rng: random.Random) -> tuple[list[str], str, int]:
    fault = rng.choices(
        ["pass", "verify_fail", "timeout", "scope_mismatch", "invalidation", "eviction", "restart", "duplicate"],
        weights=[55, 8, 8, 7, 7, 5, 5, 5], k=1)[0]
    actions = ["begin_verify"]
    scope, epoch = "scope-ok", 1
    if fault == "pass":
        actions += ["verify_pass", "commit"]
    elif fault == "duplicate":
        actions += ["duplicate", "verify_pass", "duplicate", "commit", "duplicate"]
    elif fault == "scope_mismatch":
        scope = "scope-bad"; actions += ["verify_pass"]
    else:
        actions += [fault]
    return actions, scope, epoch


def run_clients(transactions: int, clients: int, seed: int) -> dict[str, object]:
    machine = PSTPStateMachine()
    def run_one(index: int) -> Counter[str]:
        rng = random.Random(seed * 1_000_003 + index)
        actions, scope, epoch = sequence(rng)
        blocks = tuple(range(index * 8, index * 8 + rng.randint(1, 8)))
        txn_id = f"c{index % clients}-txn-{index:06d}"
        machine.open(Transaction(txn_id, blocks, "scope-ok", 1))
        for action in actions:
            machine.apply(txn_id, action, scope=scope, epoch=epoch)
        return Counter({action: 1 for action in actions})

    counts: Counter[str] = Counter()
    with ThreadPoolExecutor(max_workers=clients) as pool:
        for partial in pool.map(run_one, range(transactions)):
            counts.update(partial)
    failures = machine.audit()
    terminal = Counter(txn.state.value for txn in machine.transactions)
    return {
        "clients": clients, "transactions": transactions, "seed": seed,
        "final_states": dict(terminal), "actions": dict(counts),
        "committed": terminal[State.COMMITTED.value], "aborted": terminal[State.ABORTED.value],
        "invariant_failures": len(failures), "failure_examples": failures[:20],
        "pass": not failures,
        "claim_boundary": "Deterministic in-memory PSTP state-machine stress; live scheduler fault probes remain separately reported.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transactions", type=int, default=100_000)
    parser.add_argument("--clients", default="1,8,32")
    parser.add_argument("--seed", type=int, default=20260722)
    parser.add_argument("--csv-output", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    args = parser.parse_args()
    rows = [run_clients(args.transactions, int(value), args.seed) for value in args.clients.split(",")]
    args.csv_output.parent.mkdir(parents=True, exist_ok=True)
    with args.csv_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "clients", "transactions", "seed", "committed", "aborted", "invariant_failures", "pass", "final_states", "actions", "claim_boundary"])
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "clients": row["clients"], "transactions": row["transactions"], "seed": row["seed"],
                "committed": row["committed"], "aborted": row["aborted"],
                "invariant_failures": row["invariant_failures"], "pass": row["pass"],
                "final_states": json.dumps(row["final_states"], sort_keys=True),
                "actions": json.dumps(row["actions"], sort_keys=True),
                "claim_boundary": row["claim_boundary"],
            })
    args.json_output.write_text(json.dumps({"schema_version": "pstp-stress-v1", "rows": rows}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(rows, indent=2))
    return 1 if any(not row["pass"] for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
