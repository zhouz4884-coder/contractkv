#!/usr/bin/env python3
"""Exercise the CacheSlide artifact's native run_one path on local Llama weights."""

from __future__ import annotations

import argparse
import importlib.util
import json
import time
from pathlib import Path


def load_artifact(path: Path):
    spec = importlib.util.spec_from_file_location("cacheslide_artifact", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load CacheSlide artifact from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.80)
    args = parser.parse_args()

    started = time.perf_counter()
    result = {
        "schema_version": "contractkv.external.cacheslide-smoke.v1",
        "artifact": str(args.artifact),
        "model": args.model,
        "status": "error",
    }
    try:
        artifact = load_artifact(args.artifact)
        llm = artifact.LLM(
            model=args.model,
            dtype="float16",
            gpu_memory_utilization=args.gpu_memory_utilization,
            max_model_len=4096,
            enforce_eager=True,
        )
        tokenizer = artifact.AutoTokenizer.from_pretrained(args.model)
        core = artifact.get_vllm_core_model(llm)
        layers = artifact.get_decoder_layers(core)
        result.update({
            "model_loaded": True,
            "cache_fuse_metadata_present": isinstance(
                getattr(core, "cache_fuse_metadata", None), dict
            ),
            "hack_kv_layers": sum(
                hasattr(layer.self_attn, "hack_kv") for layer in layers
            ),
            "decoder_layers": len(layers),
        })
        cached_text, cached_ttft, normal_text, normal_ttft = artifact.run_one(
            llm,
            tokenizer,
            [
                "Paris is the capital of France. This fact is stable.",
                "Berlin is the capital of Germany. This fact is also stable.",
            ],
            "What is the capital of France? Answer with the city only.",
            max_new_tokens=8,
        )
        result.update({
            "status": "success",
            "cached_text": cached_text,
            "normal_text": normal_text,
            "cached_ttft_ms": cached_ttft * 1000.0,
            "normal_ttft_ms": normal_ttft * 1000.0,
            "quality_match": cached_text.strip().lower() == normal_text.strip().lower(),
        })
    except Exception as exc:
        result.update({
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        })
    result["wall_time_s"] = time.perf_counter() - started
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
