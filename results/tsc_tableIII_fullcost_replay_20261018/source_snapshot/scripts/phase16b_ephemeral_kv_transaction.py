#!/usr/bin/env python3
"""Phase 16B ephemeral KV transaction correctness model."""

from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


EVENT_FIELDS = [
    "cycle",
    "case",
    "state",
    "allocated_blocks",
    "promoted_blocks",
    "freed_blocks",
    "global_cache_size_before",
    "global_cache_size_after",
    "leak_detected",
    "stale_hash_pointer",
    "transaction_metadata_leak",
    "operation_ms",
    "notes",
]

SUMMARY_FIELDS = [
    "cycles",
    "commit_cases",
    "abort_cases",
    "duplicate_commit_cases",
    "partial_block_cases",
    "block_leak_count",
    "stale_hash_pointer_count",
    "promotion_p95_ms",
    "rollback_p95_ms",
    "cache_table_inconsistency_count",
    "transaction_metadata_leak_count",
    "active_transaction_count_after_run",
    "gate_pass",
    "claim_boundary",
]


@dataclass
class Block:
    block_id: int
    global_hash: str | None = None
    owner_txn: str | None = None
    allocated: bool = False


@dataclass
class ShadowTxn:
    txn_id: str
    request_id: str
    stable_prefix_end_token: int
    block_ids: list[int] = field(default_factory=list)
    canonical_hashes: list[str] = field(default_factory=list)
    state: str = "OPEN"
    created_cache_epoch: int = 0


class BlockPool:
    def __init__(self, total_blocks: int = 8192) -> None:
        self.blocks = [Block(i) for i in range(total_blocks)]
        self.free = list(range(total_blocks))
        self.cached_block_hash_to_block: dict[str, int] = {}
        self.shadow_txns: dict[str, ShadowTxn] = {}
        self.ephemeral_block_owner: dict[int, str] = {}
        self.cache_epoch = 0

    def begin_txn(self, txn_id: str, request_id: str, stable_prefix_end_token: int) -> ShadowTxn:
        txn = ShadowTxn(txn_id, request_id, stable_prefix_end_token, created_cache_epoch=self.cache_epoch)
        self.shadow_txns[txn_id] = txn
        return txn

    def allocate_ephemeral(self, txn_id: str, canonical_hashes: list[str]) -> None:
        txn = self.shadow_txns[txn_id]
        for canonical_hash in canonical_hashes:
            block_id = self.free.pop()
            block = self.blocks[block_id]
            block.allocated = True
            block.owner_txn = txn_id
            block.global_hash = None
            txn.block_ids.append(block_id)
            txn.canonical_hashes.append(canonical_hash)
            self.ephemeral_block_owner[block_id] = txn_id

    def cache_resident(self, canonical_hash: str) -> bool:
        return canonical_hash in self.cached_block_hash_to_block

    def foreground_can_see_ephemeral(self, txn_id: str) -> bool:
        txn = self.shadow_txns[txn_id]
        visible_blocks = set(self.cached_block_hash_to_block.values())
        return any(block_id in visible_blocks for block_id in txn.block_ids)

    def commit(self, txn_id: str, stable_full_blocks: int) -> tuple[int, int]:
        txn = self.shadow_txns[txn_id]
        txn.state = "VERIFYING"
        promoted = 0
        freed = 0
        for offset, block_id in enumerate(list(txn.block_ids)):
            block = self.blocks[block_id]
            canonical_hash = txn.canonical_hashes[offset]
            if offset < stable_full_blocks:
                existing = self.cached_block_hash_to_block.get(canonical_hash)
                if existing is not None:
                    self._free_ephemeral(block_id)
                    freed += 1
                else:
                    block.owner_txn = None
                    block.global_hash = canonical_hash
                    self.cached_block_hash_to_block[canonical_hash] = block_id
                    self.ephemeral_block_owner.pop(block_id, None)
                    promoted += 1
            else:
                self._free_ephemeral(block_id)
                freed += 1
        txn.state = "COMMITTED"
        self.cache_epoch += 1
        self.shadow_txns.pop(txn_id, None)
        return promoted, freed

    def abort(self, txn_id: str) -> int:
        txn = self.shadow_txns[txn_id]
        txn.state = "ABORTED"
        freed = 0
        for block_id in list(txn.block_ids):
            if block_id in self.ephemeral_block_owner:
                self._free_ephemeral(block_id)
                freed += 1
        self.cache_epoch += 1
        self.shadow_txns.pop(txn_id, None)
        return freed

    def _free_ephemeral(self, block_id: int) -> None:
        block = self.blocks[block_id]
        block.allocated = False
        block.global_hash = None
        block.owner_txn = None
        self.ephemeral_block_owner.pop(block_id, None)
        self.free.append(block_id)

    def leak_count(self) -> int:
        return sum(1 for block_id, owner in self.ephemeral_block_owner.items() if self.blocks[block_id].owner_txn != owner)

    def stale_hash_pointers(self) -> int:
        stale = 0
        for canonical_hash, block_id in self.cached_block_hash_to_block.items():
            block = self.blocks[block_id]
            if not block.allocated or block.global_hash != canonical_hash:
                stale += 1
        return stale


def make_hashes(case: str, cycle: int, blocks: int, duplicate_prefix: str | None = None) -> list[str]:
    if duplicate_prefix:
        return [f"{duplicate_prefix}:b{i}" for i in range(blocks)]
    return [f"{case}:c{cycle}:b{i}" for i in range(blocks)]


def run_cycle(pool: BlockPool, cycle: int, rng: random.Random) -> dict[str, Any]:
    case = rng.choice(["commit", "abort", "duplicate_commit", "partial_block", "cancellation"])
    total_blocks = rng.choice([128, 256, 384])
    stable_blocks = rng.randint(total_blocks // 2, total_blocks)
    if case == "partial_block":
        stable_blocks = max(1, total_blocks - 1)
    duplicate_prefix = "shared-duplicate" if case == "duplicate_commit" else None
    txn_id = f"txn-{cycle}"
    before = len(pool.cached_block_hash_to_block)
    txn = pool.begin_txn(txn_id, f"req-{cycle}", stable_blocks * 16)
    pool.allocate_ephemeral(txn.txn_id, make_hashes(case, cycle, total_blocks, duplicate_prefix))
    invisible_before = not pool.foreground_can_see_ephemeral(txn_id)
    started = time.perf_counter()
    promoted = 0
    if case in {"abort", "cancellation"}:
        freed = pool.abort(txn_id)
        state = "ABORTED"
    else:
        promoted, freed = pool.commit(txn_id, stable_blocks)
        state = "COMMITTED"
    elapsed = (time.perf_counter() - started) * 1000.0
    leak = pool.leak_count()
    stale = pool.stale_hash_pointers()
    metadata_leak = txn_id in pool.shadow_txns
    visible_after_commit = state == "COMMITTED" and promoted > 0
    clean_abort = state == "ABORTED" and before == len(pool.cached_block_hash_to_block)
    notes = []
    if not invisible_before:
        notes.append("ephemeral_visible_before_commit")
    if state == "COMMITTED" and not visible_after_commit and case != "duplicate_commit":
        notes.append("commit_not_visible")
    if state == "ABORTED" and not clean_abort:
        notes.append("abort_changed_global_cache")
    if metadata_leak:
        notes.append("transaction_metadata_leak")
    return {
        "cycle": cycle,
        "case": case,
        "state": state,
        "allocated_blocks": total_blocks,
        "promoted_blocks": promoted,
        "freed_blocks": freed,
        "global_cache_size_before": before,
        "global_cache_size_after": len(pool.cached_block_hash_to_block),
        "leak_detected": leak,
        "stale_hash_pointer": stale,
        "transaction_metadata_leak": metadata_leak,
        "operation_ms": round(elapsed, 6),
        "notes": ";".join(notes),
    }


def summarize(rows: list[dict[str, Any]], active_transaction_count: int = 0) -> dict[str, Any]:
    promotions = [float(row["operation_ms"]) for row in rows if row["state"] == "COMMITTED"]
    rollbacks = [float(row["operation_ms"]) for row in rows if row["state"] == "ABORTED"]
    block_leaks = sum(1 for row in rows if int(row["leak_detected"]) != 0)
    stale = sum(1 for row in rows if int(row["stale_hash_pointer"]) != 0)
    inconsistent = sum(1 for row in rows if row["notes"])
    metadata_leaks = sum(1 for row in rows if row.get("transaction_metadata_leak"))
    return {
        "cycles": len(rows),
        "commit_cases": sum(1 for row in rows if row["case"] == "commit"),
        "abort_cases": sum(1 for row in rows if row["case"] in {"abort", "cancellation"}),
        "duplicate_commit_cases": sum(1 for row in rows if row["case"] == "duplicate_commit"),
        "partial_block_cases": sum(1 for row in rows if row["case"] == "partial_block"),
        "block_leak_count": block_leaks,
        "stale_hash_pointer_count": stale,
        "promotion_p95_ms": round(percentile(promotions, 0.95), 6),
        "rollback_p95_ms": round(percentile(rollbacks, 0.95), 6),
        "cache_table_inconsistency_count": inconsistent,
        "transaction_metadata_leak_count": metadata_leaks,
        "active_transaction_count_after_run": active_transaction_count,
        "gate_pass": block_leaks == 0 and stale == 0 and inconsistent == 0 and metadata_leaks == 0 and active_transaction_count == 0 and percentile(promotions, 0.95) < 1.0 and percentile(rollbacks, 0.95) < 1.0,
        "claim_boundary": "In-memory transactional KV namespace model; not yet installed inside vLLM block_pool.",
    }


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    pos = (len(values) - 1) * pct
    lo = int(pos)
    hi = min(lo + 1, len(values) - 1)
    frac = pos - lo
    return values[lo] * (1 - frac) + values[hi] * frac


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{field: row.get(field, "") for field in fields} for row in rows])


def run(args: argparse.Namespace) -> None:
    rng = random.Random(args.seed)
    pool = BlockPool(total_blocks=args.total_blocks)
    rows = [run_cycle(pool, cycle, rng) for cycle in range(args.cycles)]
    write_csv(args.summary_output, [summarize(rows, len(pool.shadow_txns))], SUMMARY_FIELDS)
    args.events_output.parent.mkdir(parents=True, exist_ok=True)
    with args.events_output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycles", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=16101)
    parser.add_argument("--total-blocks", type=int, default=524288)
    parser.add_argument("--events-output", type=Path, default=Path("results/runtime/phase16b_ephemeral_kv_transaction_events_v0.jsonl"))
    parser.add_argument("--summary-output", type=Path, default=Path("results/runtime/phase16b_ephemeral_kv_transaction_summary_v0.csv"))
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
