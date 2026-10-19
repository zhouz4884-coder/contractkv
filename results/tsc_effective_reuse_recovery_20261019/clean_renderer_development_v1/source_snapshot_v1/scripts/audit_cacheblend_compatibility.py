#!/usr/bin/env python3
"""Record the exact compatibility chain used for the CacheBlend baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path


HIT_RE = re.compile(r"LMCache hit tokens:\s*(\d+)")


def run(command: list[str], env: dict[str, str] | None = None) -> dict[str, object]:
    proc = subprocess.run(command, text=True, capture_output=True, env=env, check=False)
    return {"command": command, "returncode": proc.returncode,
            "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--flashinfer-root", type=Path, required=True)
    parser.add_argument("--nvcc", type=Path, required=True)
    parser.add_argument("--positional-encoding", type=Path, required=True)
    parser.add_argument("--log-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    env = dict(os.environ)
    env["PYTHONPATH"] = str(args.flashinfer_root)
    versions = run([str(args.python), "-c",
                    "from importlib.metadata import version; import flashinfer,torch,vllm; "
                    "print(f'flashinfer={flashinfer.__version__}'); "
                    "print(f'lmcache={version(\"lmcache\")}'); "
                    "print(f'torch={torch.__version__}'); print(f'vllm={vllm.__version__}')"], env)
    api = run([str(args.python), "-c",
               "from flashinfer.page import block_sparse_indices_to_vector_sparse_offsets; "
               "from flashinfer.utils import check_shape_dtype_device,device_support_pdl; print('compatible')"], env)
    nvcc = run([str(args.nvcc), "--version"])
    source = args.positional_encoding.read_text(encoding="utf-8")

    repeats = []
    all_hits: list[int] = []
    for repeat in range(1, 6):
        log = args.log_directory / f"llama-r{repeat}-cacheblend.log"
        text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
        hits = [int(value) for value in HIT_RE.findall(text)]
        all_hits.extend(hits)
        repeats.append({
            "repeat": repeat, "log_present": log.exists(), "hit_events": len(hits),
            "positive_hit_events": sum(value > 0 for value in hits),
            "engine_fatal_errors": text.count("EngineCore encountered a fatal error"),
            "http_500": text.count("500 Internal Server Error"),
        })

    payload = {
        "schema_version": "contractkv.cacheblend-compatibility-audit.v1",
        "versions": versions, "required_flashinfer_api": api, "nvcc": nvcc,
        "fp16_validation_patch_installed": "CONTRACTKV_LMCACHE_FP16_VALIDATION_V1" in source,
        "positional_encoding_sha256": sha256(args.positional_encoding),
        "cacheblend_chunk_size": 32,
        "separator": "<|reserved_special_token_0|>",
        "repeats": repeats,
        "total_hit_events": len(all_hits),
        "positive_hit_event_rate": sum(value > 0 for value in all_hits) / max(1, len(all_hits)),
        "claim_boundary": (
            "The patch changes only LMCache's hard-coded BF16 RoPE validation tensors to the frozen FP16 dtype. "
            "The cache lookup, sparse attention, blend, and serving request paths remain upstream LMCache."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if api["returncode"] == 0 and nvcc["returncode"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
