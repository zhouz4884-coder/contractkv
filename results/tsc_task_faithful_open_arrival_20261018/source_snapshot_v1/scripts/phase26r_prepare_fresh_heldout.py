#!/usr/bin/env python3
"""Build a source-disjoint Phase 26R held-out set from the full local datasets."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


FAMILIES = ("ruler", "hotpotqa", "narrativeqa", "qasper", "repobench")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def segment(kind: str, text: str) -> dict[str, Any]:
    return {"type": kind, "text": text, "token_count": len(text.split())}


def family(row: dict[str, Any]) -> str:
    if row.get("dataset") == "RULER":
        return "ruler"
    if row.get("dataset") == "RepoBench":
        return "repobench"
    return str(row.get("task", ""))


def prior_ids(paths: list[Path]) -> dict[str, set[str]]:
    result = {key: set() for key in FAMILIES}
    for path in paths:
        if not path.exists():
            continue
        for row in read_jsonl(path):
            key = family(row)
            if key in result:
                result[key].add(str(row.get("sample_id")))
    return result


def longbench_row(task: str, index: int, row: dict[str, Any]) -> dict[str, Any]:
    system = f"Answer the LongBench {task} question from the supplied context."
    context = str(row.get("context", ""))
    query = str(row.get("input", ""))
    pieces = [segment("SYS_PROMPT", system), segment("RAG_CHUNK", context),
              segment("USER_QUERY", query)]
    return {
        "dataset": "LongBench", "task": task, "sample_id": str(index),
        "total_prompt_tokens": sum(piece["token_count"] for piece in pieces),
        "segments": pieces, "answer": row.get("answers", []),
        "metadata": {"source": "THUDM/LongBench full local snapshot", "split": "test",
                     "evaluation_ready": True, "phase26r_source_index": index},
    }


def repo_context(row: dict[str, Any]) -> str:
    value = row.get("context") or row.get("cross_file_context") or []
    if isinstance(value, str):
        return value
    chunks = []
    for item in value:
        if isinstance(item, dict):
            chunks.append(f"# Path: {item.get('path', '')}\n{item.get('snippet', item.get('code', ''))}")
        else:
            chunks.append(str(item))
    return "\n\n".join(chunks)


def repobench_row(index: int, row: dict[str, Any]) -> dict[str, Any]:
    context = repo_context(row)
    prefix = "\n".join(str(row.get(field, "")) for field in
                       ("file_path", "import_statement", "cropped_code", "input")
                       if row.get(field))
    answer = (row.get("next_line") or row.get("target") or row.get("answer")
              or row.get("ground_truth") or "")
    pieces = [segment("REPO_CONTEXT", context), segment("CODE_PREFIX", prefix),
              segment("USER_QUERY", "Complete the next line of Python code.")]
    return {
        "dataset": "RepoBench", "task": "python_v1.1", "sample_id": str(index),
        "total_prompt_tokens": sum(piece["token_count"] for piece in pieces),
        "segments": pieces, "answer": answer,
        "metadata": {"source": "tianyang/repobench_python_v1.1 full local snapshot",
                     "split": "cross_file_first", "evaluation_ready": True,
                     "phase26r_source_index": index},
    }


def ruler_row(index: int) -> dict[str, Any]:
    key = f"phase26r-lantern-{index}"
    answer = str(8800000 + index)
    context = (("The archive contains neutral facts. "
                f"The special magic number for {key} is {answer}. "
                "This sentence preserves a stable retrieval context. ") * 24)
    pieces = [
        segment("SYS_PROMPT", "Find the hidden special magic number and return only its value."),
        segment("SYNTHETIC_CONTEXT", context),
        segment("USER_QUERY", f"What is the special magic number for {key}?"),
    ]
    return {
        "dataset": "RULER", "task": "niah_single_1", "sample_id": str(index),
        "total_prompt_tokens": sum(piece["token_count"] for piece in pieces),
        "segments": pieces, "answer": answer,
        "metadata": {"source": "Phase26R preregistered RULER generator",
                     "evaluation_ready": True, "phase26r_source_index": index},
    }


def choose(rows: list[dict[str, Any]], count: int, salt: str, key: str,
           excluded: set[str]) -> list[tuple[int, dict[str, Any]]]:
    candidates = [(index, row) for index, row in enumerate(rows)
                  if str(index) not in excluded]
    candidates.sort(key=lambda pair: hashlib.sha256(
        f"{salt}:{key}:{pair[0]}".encode()).hexdigest())
    if len(candidates) < count:
        raise RuntimeError(f"insufficient fresh {key} records: {len(candidates)}/{count}")
    return candidates[:count]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--longbench-root", type=Path, required=True)
    parser.add_argument("--repobench-arrow", type=Path, required=True)
    parser.add_argument("--prior-sessions", type=Path, action="append", default=[])
    parser.add_argument("--per-family", type=int, default=10)
    parser.add_argument("--selection-salt", default="phase26r-fresh-heldout-v1")
    parser.add_argument("--ruler-base", type=int, default=10000)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--commitment", type=Path, required=True)
    args = parser.parse_args()
    excluded = prior_ids(args.prior_sessions)
    selected: list[dict[str, Any]] = []

    for offset in range(args.per_family):
        index = args.ruler_base + offset
        if str(index) in excluded["ruler"]:
            raise RuntimeError(f"RULER held-out overlap at generated index {index}")
        selected.append(ruler_row(index))
    for task in ("hotpotqa", "narrativeqa", "qasper"):
        source = read_jsonl(args.longbench_root / f"{task}.jsonl")
        for index, row in choose(source, args.per_family, args.selection_salt, task, excluded[task]):
            selected.append(longbench_row(task, index, row))

    from datasets import Dataset
    repo = Dataset.from_file(str(args.repobench_arrow))
    repo_rows = [dict(repo[index]) for index in range(len(repo))]
    for index, row in choose(repo_rows, args.per_family, args.selection_salt,
                             "repobench", excluded["repobench"]):
        selected.append(repobench_row(index, row))

    for row in selected:
        key = family(row)
        sid = f"phase26r-{key}-{row['sample_id']}"
        row.update({"phase22r_family": key, "phase22r_session_id": sid,
                    "phase19b_session_id": sid, "phase22r_partition": "heldout_sealed"})
    selected.sort(key=lambda row: (FAMILIES.index(family(row)), str(row["sample_id"])))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n"
                                   for row in selected), encoding="utf-8")
    payload = {
        "schema_version": "contractkv.phase26r.fresh-heldout.v1",
        "selection_salt": args.selection_salt,
        "heldout_count": len(selected),
        "per_family": args.per_family,
        "heldout_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "prior_paths": [str(path) for path in args.prior_sessions],
        "prior_sample_id_overlap": sum(
            str(row["sample_id"]) in excluded[family(row)] for row in selected),
        "heldout_opened_for_tuning": False,
    }
    args.commitment.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
