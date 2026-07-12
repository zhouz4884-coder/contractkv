#!/usr/bin/env python3
"""Inspect one real vLLM completion prompt-logprob alignment without retokenizing output."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase17_calibration_rerun import load_jsonl, prompt_ids, sample_key
from scripts.phase17_live_common import post_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--full-pool", type=Path, default=Path("results/workload/phase14d_full_pool_v2.jsonl"))
    parser.add_argument("--jobs", type=Path, default=Path("results/end_to_end/phase14r_quality_jobs_v5.jsonl"))
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=True)
    jobs = [row for row in load_jsonl(args.jobs) if row.get("policy") != "raw-order"]
    samples = {sample_key(row): row for row in load_jsonl(args.full_pool)}
    raws = {row.get("sample_key"): row for row in load_jsonl(args.raw) if row.get("error_type") == "none"}
    job = next(row for row in jobs if row["sample_key"] in raws)
    ids, messages = prompt_ids(job, samples[job["sample_key"]], tokenizer, 8192)
    raw = raws[job["sample_key"]]
    raw_ids = [int(value) for value in raw["token_ids"]]
    result = {"job": {key: job.get(key) for key in ("job_id", "sample_key", "candidate_id")}, "candidate_prompt_tokens": len(ids), "raw_answer_tokens": len(raw_ids)}
    raw_response = post_json(args.base_url.rstrip("/") + "/chat/completions", {
        "model": args.model, "messages": messages, "max_tokens": 96,
        "temperature": 0, "logprobs": True, "top_logprobs": 2, "return_token_ids": True,
        "request_id": "phase17-debug-raw",
    }, 300)
    choice = (raw_response.get("choices") or [{}])[0]
    result["fresh_raw"] = {"finish_reason": choice.get("finish_reason"), "stop_reason": choice.get("stop_reason"), "token_ids": choice.get("token_ids")}
    for stop_id in (151643, 151645):
        forced = ids + raw_ids + [stop_id]
        response = post_json(args.base_url.rstrip("/") + "/completions", {
            "model": args.model, "prompt": forced, "max_tokens": 1,
            "temperature": 0, "prompt_logprobs": 2, "return_token_ids": True,
            "request_id": f"phase17-debug-{stop_id}",
        }, 300)
        completion = (response.get("choices") or [{}])[0]
        logs = completion.get("prompt_logprobs") or []
        rows = []
        for index in [len(ids) - 1, len(ids), len(ids) + 1, len(ids) + len(raw_ids) - 2, len(ids) + len(raw_ids) - 1, len(ids) + len(raw_ids)]:
            if 0 <= index < len(logs):
                entry = logs[index] or {}
                rows.append({"index": index, "ids": list(entry.keys()), "ranks": [value.get("rank") for value in entry.values()]})
        result[str(stop_id)] = {"returned_prompt_len": len(completion.get("prompt_token_ids") or []), "logprob_len": len(logs), "rows": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
