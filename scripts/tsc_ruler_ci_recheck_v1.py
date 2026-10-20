"""Read-only replay of the original RULER CI and its recorded sensitivity.

No inference, new bootstrap selection, manuscript edits, or historical writes.
The 2026-10-18 bootstrap implementation is replayed with its original seeds;
request pairing, source identity, and the point estimand are checked separately.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import tsc_revision_remaining_stats_audit_v1 as historical
from scripts.prepare_extended_ruler_sessions import digest_rows

AUDIT = ROOT / "results/tsc_revision_remaining_audit_20261018"
EXPECTED_SESSIONS_SHA = "7fe10a55f82056125b6acb478aa24bd4883c12c4f6bfd19b3dedfd1f6e13f616"
MODEL_ROOTS = {
    "Qwen3-8B": "results/submission_supplement/common_ruler/qwen",
    "Mistral-7B-Instruct-v0.3": "results/submission_supplement/common_ruler/mistral",
    "Llama-3.1-8B-Instruct": "results/submission_supplement/ruler_extended",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jsonl(data: bytes) -> list[dict]:
    return [json.loads(line) for line in data.splitlines() if line.strip()]


def direct_point(raw: list[dict], compiled: list[dict]) -> float:
    """Independent expression of the historical cell's recorded estimand."""
    r = [row for row in raw if row["row_type"] == "future"]
    c = [row for row in compiled if row["row_type"] == "future"]
    unhidden = sum(float(row.get("unhidden_verifier_ms") or 0)
                   for row in compiled if row["row_type"] == "canary")
    issued = sum(row.get("certificate_issued") is True for row in c)
    return 100 * (1 - (statistics.fmean(float(x["ttft_ms"]) for x in c)
                      + unhidden / max(issued, 1))
                  / statistics.fmean(float(x["ttft_ms"]) for x in r))


def run(output: Path) -> dict:
    if output.exists():
        raise FileExistsError(f"Refuse to overwrite a previous recheck: {output}")
    retrieval = json.loads((AUDIT / "retrieval_manifest_v1.json").read_text())
    selected = [r for r in retrieval["files"] if any(
        r["remote_path"].startswith(base + "/") for base in MODEL_ROOTS.values())
        or r["remote_path"] == "results/submission_supplement/ruler_extended_sessions_v0.jsonl"]
    assert len(selected) == 19
    decoded = {}
    input_receipts = []
    for row in selected:
        p = ROOT / row["local_path"]
        compressed = p.read_bytes()
        data = gzip.decompress(compressed)
        assert row["mode"] == "verbatim_gzip"
        assert hashlib.sha256(compressed).hexdigest() == row["gzip_sha256"]
        assert hashlib.sha256(data).hexdigest() == row["decompressed_sha256"] == row["remote_sha256"]
        assert len(data) == row["remote_bytes"]
        decoded[row["remote_path"]] = jsonl(data)
        input_receipts.append({"path": row["local_path"], "gzip_sha256": sha(p),
                               "original_sha256": row["remote_sha256"]})

    sessions = decoded["results/submission_supplement/ruler_extended_sessions_v0.jsonl"]
    assert digest_rows(sessions) == EXPECTED_SESSIONS_SHA
    ids = {row["phase19b_session_id"] for row in sessions}
    assert len(sessions) == len(ids) == 30
    assert len({row["metadata"]["source_group_id"] for row in sessions}) == 30
    expected_keys = {(sid, turn) for sid in ids for turn in range(1, 10)}
    cells = []
    points = {}
    for model, base in MODEL_ROOTS.items():
        parts = []
        for repeat in (1, 2, 3):
            raw = decoded[f"{base}/repeat{repeat}/raw-order.jsonl"]
            compiled = decoded[f"{base}/repeat{repeat}/contractkv-full.jsonl"]
            for arm, initial_type in ((raw, "warmup"), (compiled, "canary")):
                assert len(arm) == 300 and all(row["success"] is True for row in arm)
                future = [row for row in arm if row["row_type"] == "future"]
                keys = Counter((row["session_id"], row["turn_id"]) for row in future)
                assert set(keys) == expected_keys and set(keys.values()) == {1}
                assert all(row["dataset"] == "RULER" and row["task"] == "niah_single_1" for row in arm)
                initial = Counter(row["session_id"] for row in arm if row["row_type"] == initial_type)
                assert set(initial) == ids and set(initial.values()) == {1}
            point = direct_point(raw, compiled)
            parts.append(point)
            cells.append({"model": model, "repeat": repeat, "paired_future_requests": 270,
                          "raw_warmups": 30, "contract_canaries": 30,
                          "net_mean_ttft_reduction_pct": point})
        points[model] = statistics.fmean(parts)

    # Redirect only the historical function's output sink, leaving all old files
    # untouched. The routine asserts original estimates/CIs against July output.
    captured = {}
    old_dump = historical.dump
    try:
        historical.dump = lambda name, data: captured.update({name: data})
        historical.ruler()
    finally:
        historical.dump = old_dump
    replay = captured["ruler_ci_audit_v1.json"]
    saved = json.loads((AUDIT / "ruler_ci_audit_v1.json").read_text())
    assert replay == saved, "Historical replay/sensitivity has drifted"
    for row in replay["models"]:
        assert abs(row["point_pct"] - points[row["model"]]) < 1e-10
    assert abs(statistics.fmean(points.values()) - replay["macro_point_pct"]) < 1e-10
    # Neither the prior sensitivity nor the data hashes may change in this run.
    assert saved == json.loads((AUDIT / "ruler_ci_audit_v1.json").read_text())
    for row in input_receipts:
        assert sha(ROOT / row["path"]) == row["gzip_sha256"]

    receipt = {
        "status": "PASS", "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "recheck_script_sha256": sha(Path(__file__)),
        "historical_script_sha256": sha(Path(historical.__file__)),
        "frozen_sessions_canonical_sha256": EXPECTED_SESSIONS_SHA,
        "raw_input_files_verified": len(selected), "unique_source_sessions": 30,
        "fixed_models": list(MODEL_ROOTS), "fresh_process_pairs_per_model": 3,
        "future_turns_per_session": 9, "paired_future_requests": 2430,
        "live_business_and_canary_records_both_arms": 5400,
        "all_original_pairs_retained": True, "original_files_unchanged": True,
        "historical_and_sensitivity_replay_matches_saved_result": True,
        "bootstrap_draws_per_interval": 10000,
        "replayed_result": replay, "independent_point_checks": cells,
        "between_model_point_range_pct": [min(points.values()), max(points.values())],
        "between_model_point_spread_percentage_points": max(points.values()) - min(points.values()),
        "unseen_model_generalization_CI": None,
        "unseen_model_limit": "Three fixed, non-randomly selected models do not identify a model-population prediction interval.",
        "estimand": "Equal-weight mean across three model means, each an equal-weight mean over three process-pair TTFT reductions. Preserve original recorded unhidden-verifier accounting.",
        "protocol_limit": "Original qualified RULER / 6000 ms tool-slack protocol, not strict raw-witness zero-slack complete wall.",
        "input_receipts": input_receipts, "new_GPU_requests": 0,
    }
    output.mkdir(parents=True)
    (output / "recheck_receipt_v1.json").write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    receipt = run(args.output_dir.resolve())
    print(json.dumps({k: receipt[k] for k in (
        "status", "raw_input_files_verified", "paired_future_requests",
        "historical_and_sensitivity_replay_matches_saved_result", "new_GPU_requests")}, indent=2))


if __name__ == "__main__":
    main()
