"""Save runtime, input, model-geometry and source identity before a live cell."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess

def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""): h.update(chunk)
    return h.hexdigest()

def main():
    p = argparse.ArgumentParser(); p.add_argument("--root", type=Path, required=True)
    p.add_argument("--source", type=Path, required=True); p.add_argument("--model", type=Path, required=True)
    p.add_argument("--sessions", type=Path, required=True); p.add_argument("--output", type=Path, required=True)
    p.add_argument("--cell", required=True); p.add_argument("--gpu", required=True); p.add_argument("--budget", type=int, required=True)
    a = p.parse_args(); config = json.loads((a.model / "config.json").read_text())
    files = [a.root / "configs/tsc_major_revision_r1_protocol.json", a.root / "scripts/tsc_revision_live.py",
             a.root / "scripts/run_tsc_revision_r1_cell.sh", a.sessions, a.model / "config.json",
             a.model / "tokenizer_config.json", a.source / "vllm/v1/core/sched/scheduler.py"]
    indexed = json.loads((a.model / "model.safetensors.index.json").read_text())
    missing = [name for name in set(indexed["weight_map"].values()) if not (a.model / name).is_file()]
    if missing: raise RuntimeError("Missing model weight shards: " + str(missing))
    record = {"schema_version": "tsc-revision-cell-manifest.v1", "timestamp": datetime.now(timezone.utc).isoformat(),
              "cell": a.cell, "gpu_ids": a.gpu, "output_budget_override": a.budget,
              "sources": [{"path": str(path), "sha256": sha(path)} for path in files],
              "model_path": str(a.model), "model_geometry": {k: config.get(k) for k in ["model_type", "num_hidden_layers", "num_attention_heads", "num_key_value_heads", "head_dim", "hidden_size"]},
              "indexed_shards_present": len(set(indexed["weight_map"].values())),
              "model_index_sha256": sha(a.model / "model.safetensors.index.json"),
              "packages": {k: importlib.metadata.version(k) for k in ["torch", "vllm", "transformers", "triton", "numpy"]},
              "cache_environment": {k: os.environ.get(k) for k in ["TMPDIR", "HF_HOME", "VLLM_CACHE_ROOT", "TRITON_CACHE_DIR", "TORCHINDUCTOR_CACHE_DIR"]},
              "gpu_snapshot": subprocess.run(["nvidia-smi", "--query-gpu=index,name,uuid,memory.total,memory.used,driver_version", "--format=csv"], capture_output=True, text=True, check=True).stdout}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

if __name__ == "__main__": main()
