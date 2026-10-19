"""Materialize the frozen 20-session zero-slack controlled service cohort."""
import argparse
from collections import defaultdict
import json
from pathlib import Path

def main():
    p = argparse.ArgumentParser(); p.add_argument("--root", type=Path, required=True); a = p.parse_args()
    rows = [json.loads(line) for line in (a.root / "results/tsc_service/quality/tsc_service_quality_sessions_v0.jsonl").read_text().splitlines() if line.strip()]
    by_family = defaultdict(list)
    for row in rows: by_family[row["tsc_family"]].append(row)
    selected = [row for family in sorted(by_family) for row in sorted(by_family[family], key=lambda row: row["tsc_session_id"])[:4]]
    if len(selected) != 20: raise ValueError("Expected four tenants per five frozen service templates")
    target = a.root / "results/tsc_revision_r1/inputs"; target.mkdir(parents=True, exist_ok=True)
    (target / "service_sessions_v1.jsonl").write_text("".join(json.dumps(row) + "\n" for row in selected))
    base = json.loads((a.root / "configs/tsc_service_quality_protocol.json").read_text())
    for model in ("qwen", "mistral"):
        config = dict(base)
        config["template_qualification"] = {"RULER": True, "HotpotQA": True, "NarrativeQA": True, "Qasper": False, "RepoBench": model == "qwen"}
        config["schema_version"] = "tsc.revision-zero-slack.v1"
        config["selection"] = "first four sorted tenant IDs of each original frozen template; no outcome selection"
        config["slack_ms"] = 0; config["reference_prompt"] = "raw-order"
        config["model"] = "Qwen3-8B" if model == "qwen" else "Mistral-7B-Instruct-v0.3"
        (target / ("service_" + model + "_protocol_v1.json")).write_text(json.dumps(config, indent=2) + "\n")
    print("prepared service sessions", len(selected))

if __name__ == "__main__": main()
