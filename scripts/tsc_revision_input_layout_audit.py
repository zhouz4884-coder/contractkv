"""Measure segment displacement in the frozen tokenizer's rendered prompts."""
from __future__ import annotations
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import statistics
import sys
from types import SimpleNamespace

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_live import make_turn, read_jsonl
from scripts.tsc_revision_offline_audit import write_csv


def offsets(tokenizer, messages):
    rendered = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    encoded = tokenizer(rendered, add_special_tokens=False, return_offsets_mapping=True)
    exact = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True)
    if list(encoded["input_ids"]) != list(exact):
        raise ValueError("Rendered prompt/token identity mismatch")
    return rendered, encoded["offset_mapping"], len(exact)


def main():
    p = argparse.ArgumentParser(); p.add_argument("--root", type=Path, required=True)
    p.add_argument("--model-root", type=Path, required=True); p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    from transformers import AutoTokenizer
    protocol = json.loads((a.root / "configs/tsc_major_revision_r1_protocol.json").read_text())
    inputs = a.root / "results/tsc_revision_r1/inputs"; rows = []
    for model in protocol["models"]:
        tokenizer = AutoTokenizer.from_pretrained(a.model_root / model, local_files_only=True, use_fast=True)
        for cohort, experiment in (("hotpot_heldout", "common-hotpot"), ("free_generation", "free-generation")):
            args = SimpleNamespace(protocol=protocol, experiment=experiment, model_identity=model)
            for sample in read_jsonl(inputs / (cohort + "_sessions_v1.jsonl")):
                case, raw, candidate, raw_messages, candidate_messages = make_turn(args, sample, 0)
                raw_text, raw_offsets, raw_tokens = offsets(tokenizer, raw_messages)
                cand_text, cand_offsets, candidate_tokens = offsets(tokenizer, candidate_messages)
                for segment in case["segments"]:
                    marker = "[" + segment["segment_type"] + ":" + segment["segment_id"] + "]"
                    start_raw, start_candidate = raw_text.index(marker), cand_text.index(marker)
                    text_end = start_raw + len(marker) + 1 + len(segment["text"])
                    token_raw = next(i for i, (start, end) in enumerate(raw_offsets) if start <= start_raw < end)
                    token_candidate = next(i for i, (start, end) in enumerate(cand_offsets) if start <= start_candidate < end)
                    count = sum(end > start_raw and start < text_end for start, end in raw_offsets)
                    rows.append({"model": model, "cohort": cohort, "family": sample["revision_family"],
                                 "session_id": sample["revision_session_id"], "segment_id": segment["segment_id"],
                                 "segment_type": segment["segment_type"], "raw_order_index": raw["topological_order"].index(segment["segment_id"]),
                                 "candidate_order_index": candidate["topological_order"].index(segment["segment_id"]),
                                 "raw_start_token": token_raw, "candidate_start_token": token_candidate,
                                 "displacement_tokens": token_candidate - token_raw, "segment_tokens": count,
                                 "raw_prompt_tokens": raw_tokens, "candidate_prompt_tokens": candidate_tokens,
                                 "render_token_identity_verified": True,
                                 "claim_boundary": "Offline input-position measurement with frozen tokenizer; not an attention or RoPE causality claim."})
    a.output.mkdir(parents=True, exist_ok=True); write_csv(a.output / "segment_token_displacement_v1.csv", rows)
    groups = defaultdict(list)
    for row in rows: groups[(row["model"], row["cohort"], row["family"], row["segment_type"])].append(row)
    summaries = []
    for key, values in sorted(groups.items()):
        summaries.append({"model": key[0], "cohort": key[1], "family": key[2], "segment_type": key[3],
                          "segments": len(values), "mean_raw_position": statistics.fmean(r["raw_start_token"] for r in values),
                          "mean_candidate_position": statistics.fmean(r["candidate_start_token"] for r in values),
                          "mean_displacement_tokens": statistics.fmean(r["displacement_tokens"] for r in values),
                          "raw_order_indices": json.dumps(sorted({r["raw_order_index"] for r in values})),
                          "candidate_order_indices": json.dumps(sorted({r["candidate_order_index"] for r in values}))})
    write_csv(a.output / "segment_token_displacement_summary_v1.csv", summaries)
    print(json.dumps({"segments_measured": len(rows), "token_identity_checks": True}))
    return 0

if __name__ == "__main__": raise SystemExit(main())
