"""Freeze source-disjoint revision cohorts without using outcome labels."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def family(row: dict) -> str:
    if row["dataset"] == "RULER": return "RULER"
    if row["dataset"] == "RepoBench": return "RepoBench"
    return {"hotpotqa": "HotpotQA", "narrativeqa": "NarrativeQA", "qasper": "Qasper"}[row["task"]]


def source(row: dict) -> str:
    group = str(row.get("metadata", {}).get("source_group_id", ""))
    if not group or group == "unknown": raise ValueError("Source-group provenance is required")
    return row["dataset"] + ":" + row["task"] + ":" + group


def emit(path: Path, rows: list[dict]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--pool", type=Path, required=True)
    p.add_argument("--exclude", type=Path, action="append", default=[])
    p.add_argument("--protocol", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    protocol = json.loads(a.protocol.read_text(encoding="utf-8"))
    excluded = {source(row) for path in a.exclude for row in read(path)}
    candidates = [row for row in read(a.pool) if source(row) not in excluded]
    candidates.sort(key=lambda row: hashlib.sha256((str(protocol["seed"]) + ":" + source(row)).encode()).hexdigest())
    unique = {}; cohorts = {"hotpot_development": [], "hotpot_heldout": [], "free_generation": []}
    for row in candidates:
        unique.setdefault(source(row), row)
    used = set(excluded)
    for name, count in (("hotpot_development", 5), ("hotpot_heldout", 30)):
        for key, row in unique.items():
            if key not in used and family(row) == "HotpotQA":
                cohorts[name].append(row); used.add(key)
                if len(cohorts[name]) == count: break
        if len(cohorts[name]) != count: raise ValueError("Insufficient independent source groups for " + name)
    for fam in protocol["families"]:
        selected = []
        for key, row in unique.items():
            if key not in used and family(row) == fam:
                selected.append(row); used.add(key)
                if len(selected) == protocol["free_generation"]["sessions_per_family"]: break
        if len(selected) != protocol["free_generation"]["sessions_per_family"]:
            raise ValueError("Insufficient independent source groups for " + fam)
        cohorts["free_generation"].extend(selected)
    commitments = {}
    for name, rows in cohorts.items():
        values = []
        for index, row in enumerate(rows):
            sid = "r1-" + name + "-" + hashlib.sha256(source(row).encode()).hexdigest()[:16]
            values.append({**row, "phase19b_session_id": sid, "revision_session_id": sid,
                           "revision_family": family(row), "revision_source_group": source(row)})
        path = a.output / (name + "_sessions_v1.jsonl")
        commitments[name] = {"path": path.name, "sha256": emit(path, values), "sessions": len(values),
                             "families": dict(Counter(family(row) for row in rows)),
                             "source_groups": [source(row) for row in rows]}
    report = {"schema_version": "tsc-revision-input-commitment.v1", "status": "frozen",
              "protocol_sha256": hashlib.sha256(a.protocol.read_bytes()).hexdigest(),
              "pool_sha256": hashlib.sha256(a.pool.read_bytes()).hexdigest(),
              "excluded_source_groups": len(excluded), "selection_uses_outcomes": False,
              "cohorts_disjoint": True, "cohorts": commitments}
    a.output.mkdir(parents=True, exist_ok=True)
    (a.output / "input_commitment_v1.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "cohorts"}, indent=2))
    print({k: v["sessions"] for k, v in commitments.items()})
    return 0

if __name__ == "__main__": raise SystemExit(main())
