#!/usr/bin/env python3
"""Check local model directory integrity for ContractKV phases."""

from __future__ import annotations

import argparse
import csv
import glob
import os
from pathlib import Path
from typing import Iterable


DEFAULT_MODEL_ROOT = Path(
    os.environ.get(
        "CONTRACTKV_MODEL_ROOT",
        "/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models",
    )
)
DEFAULT_MODELS = [
    "Qwen3-4B",
    "Qwen3-8B",
    "Llama-3.1-8B-Instruct",
    "Qwen3-14B",
]
DEFAULT_OPTIONAL_MODELS = {"Qwen3-14B"}
FIELDNAMES = [
    "model",
    "path",
    "exists",
    "config",
    "tokenizer",
    "generation_config",
    "num_safetensors",
    "has_index",
    "complete_for_phase",
    "allowed_incomplete",
    "blocks_phase_0_2",
]


def _has_any(files: set[str], names: Iterable[str]) -> bool:
    return any(name in files for name in names)


def collect_model_rows(
    model_root: str | Path = DEFAULT_MODEL_ROOT,
    models: Iterable[str] = DEFAULT_MODELS,
    optional_models: set[str] | None = None,
) -> list[dict[str, object]]:
    """Return one integrity row per model."""

    root = Path(model_root)
    optional = optional_models if optional_models is not None else DEFAULT_OPTIONAL_MODELS
    rows: list[dict[str, object]] = []

    for model in models:
        path = root / model
        exists = path.is_dir()
        files = set(os.listdir(path)) if exists else set()
        safetensors = glob.glob(str(path / "*.safetensors")) if exists else []
        index = glob.glob(str(path / "*.index.json")) if exists else []
        has_config = "config.json" in files
        has_tokenizer = _has_any(files, ["tokenizer.json", "tokenizer.model"])
        has_generation = "generation_config.json" in files
        has_index = len(index) > 0
        complete = exists and has_config and has_tokenizer and has_generation and len(safetensors) > 0 and has_index
        allowed_incomplete = model in optional
        rows.append(
            {
                "model": model,
                "path": str(path),
                "exists": exists,
                "config": has_config,
                "tokenizer": has_tokenizer,
                "generation_config": has_generation,
                "num_safetensors": len(safetensors),
                "has_index": has_index,
                "complete_for_phase": complete,
                "allowed_incomplete": allowed_incomplete,
                "blocks_phase_0_2": (not complete) and (not allowed_incomplete),
            }
        )

    return rows


def write_csv(rows: list[dict[str, object]], output_path: str | Path) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-root", default=str(DEFAULT_MODEL_ROOT))
    parser.add_argument("--output", default="results/env/model_integrity.csv")
    parser.add_argument("--models", nargs="*", default=DEFAULT_MODELS)
    parser.add_argument("--optional-models", nargs="*", default=sorted(DEFAULT_OPTIONAL_MODELS))
    args = parser.parse_args()

    rows = collect_model_rows(args.model_root, args.models, set(args.optional_models))
    write_csv(rows, args.output)
    for row in rows:
        print(row)

    return 1 if any(row["blocks_phase_0_2"] for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())

