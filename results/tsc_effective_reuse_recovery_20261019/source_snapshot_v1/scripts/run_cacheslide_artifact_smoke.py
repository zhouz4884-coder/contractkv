#!/usr/bin/env python3
"""Run the supplied CacheSlide run_one path without its HF dataset dependency."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrypoint", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--gpu-memory-utilization", type=float, default=.5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("cacheslide_supplied_entrypoint", args.entrypoint)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load CacheSlide entrypoint: {args.entrypoint}")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    from transformers import AutoTokenizer
    from vllm import LLM
    payload = {"entrypoint": str(args.entrypoint), "model": args.model, "runtime": "vllm-0.8.5.post1"}
    try:
        llm = LLM(model=args.model, gpu_memory_utilization=args.gpu_memory_utilization,
                  max_model_len=8192, enforce_eager=True)
        tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
        result = module.run_one(
            llm, tokenizer,
            ["Stable document alpha. " * 128, "Stable document beta. " * 128,
             "Stable document gamma. " * 128, "Stable document delta. " * 128],
            "Which stable documents were provided?", max_new_tokens=10)
        payload.update({"success": True, "result": list(result)})
    except Exception as exc:
        payload.update({"success": False, "error_type": type(exc).__name__, "error_message": str(exc)})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
