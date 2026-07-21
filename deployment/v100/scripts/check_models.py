#!/usr/bin/env python3
"""Write a machine-readable integrity audit for the V100 scale-up models."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


MODELS = {
    "qwen3-32b": "Qwen/Qwen3-32B",
    "mistral-small-24b-instruct-2501": "mistralai/Mistral-Small-24B-Instruct-2501",
    "llama-3.1-70b-instruct": "LLM-Research/Meta-Llama-3.1-70B-Instruct",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rows: list[dict[str, object]] = []
    for label, model_id in MODELS.items():
        directory = args.models_root / label
        safetensors = list(directory.glob("*.safetensors"))
        pytorch_bins = list(directory.glob("*.bin")) + list(directory.glob("*.pth"))
        has_weights = bool(safetensors or pytorch_bins)
        index_path = directory / "model.safetensors.index.json"
        if not index_path.is_file():
            index_path = directory / "pytorch_model.bin.index.json"
        has_index = index_path.is_file()
        expected_shards: set[str] = set()
        if has_index:
            try:
                expected_shards = set(json.loads(index_path.read_text(encoding="utf-8"))["weight_map"].values())
            except (KeyError, OSError, ValueError, TypeError):
                expected_shards = {"<unreadable-index>"}
        missing_shards = [name for name in expected_shards if not (directory / name).is_file()]
        rows.append(
            {
                "label": label,
                "model_id": model_id,
                "path": str(directory),
                "exists": directory.is_dir(),
                "config": (directory / "config.json").is_file(),
                "tokenizer": (directory / "tokenizer.json").is_file()
                or (directory / "tokenizer.model").is_file(),
                "generation_config": (directory / "generation_config.json").is_file(),
                "weight_files": len(safetensors) + len(pytorch_bins),
                "weight_index": has_index,
                "expected_shards": len(expected_shards),
                "missing_shards": len(missing_shards),
                "complete": directory.is_dir()
                and (directory / "config.json").is_file()
                and ((directory / "tokenizer.json").is_file() or (directory / "tokenizer.model").is_file())
                and has_weights
                and has_index
                and not missing_shards,
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for row in rows:
        print(row)
    return 0 if all(bool(row["complete"]) for row in rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
