"""Package verified raw serving evidence without credentials or model weights."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import tarfile
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_summarize import write


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(); p.add_argument("--root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True); a = p.parse_args(); root = a.root.resolve()
    evidence = root / "results/tsc_revision_r1"
    audit = json.loads((evidence / "remote_completion_audit_v1.json").read_text())
    if not audit["experimental_execution_complete"] or audit["complete_live_cells"] != 78:
        raise ValueError("Only the complete verified experiment may be packaged")
    selected = []
    for item in audit["cells"]:
        name = item["cell"]
        directory = evidence / ("service" if name.startswith("zero-slack_") else "cells") / name
        for filename in ("raw.jsonl", "summary.json", "summary.jsonl", "registration.jsonl", "metrics.jsonl", "cell_manifest.json"):
            path = directory / filename
            if path.is_file():
                selected.append(path)
        log = root / "logs/tsc_revision_r1" / (name + "_server.log")
        if not log.is_file():
            raise ValueError("Missing exact serving log " + name)
        selected.append(log)
    selected += list((evidence / "inputs").glob("*.json*"))
    selected += list((evidence / "source_snapshots").glob("*.py"))
    selected += [evidence / "guard_probe_qwen_v1.jsonl", evidence / "guard_probe_qwen14_actual_v2.jsonl"]
    selected = sorted(set(selected))
    inventory = [{"path": str(path.relative_to(root)).replace("\\", "/"),
                  "bytes": path.stat().st_size, "sha256": sha(path)} for path in selected]
    write(evidence / "raw_evidence_inventory_v1.csv", inventory)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(a.output, "w:gz", compresslevel=6) as archive:
        for path in selected:
            archive.add(path, arcname=path.relative_to(root), recursive=False)
    record = {"schema_version": "tsc-revision-raw-archive.v1", "archive": a.output.name,
              "archive_sha256": sha(a.output), "archive_bytes": a.output.stat().st_size,
              "member_files": len(selected), "uncompressed_bytes": sum(r["bytes"] for r in inventory),
              "live_cells": 78, "measured_future_requests": 25650,
              "contains_actual_output_token_ids": True, "contains_real_prefix_metric_logs": True,
              "contains_service_and_supplementary_input_commitments": True,
              "no_credentials_or_model_weights": True,
              "excluded": ["private SSH helpers", "encrypted password files", "raw network-origin resource audit",
                           "compilation caches", "superseded quarantined attempts", "model weight files"],
              "extraction": "Extract to repository root; archive members use repository-relative paths."}
    (evidence / "raw_evidence_archive_manifest_v1.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record))


if __name__ == "__main__": main()
