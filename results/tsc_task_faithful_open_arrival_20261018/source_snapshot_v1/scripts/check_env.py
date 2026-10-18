#!/usr/bin/env python3
"""Emit a JSON environment report for ContractKV Phase 0."""

from __future__ import annotations

import json
import platform
import subprocess
from typing import Any


def _command_output(command: list[str]) -> str:
    try:
        return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT).strip()
    except Exception as exc:  # pragma: no cover - hardware dependent diagnostic path.
        return f"ERROR: {type(exc).__name__}: {exc}"


def collect_env() -> dict[str, Any]:
    info: dict[str, Any] = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "nvidia_smi": _command_output(["nvidia-smi", "--query-gpu=index,name,memory.total,memory.free", "--format=csv,noheader,nounits"]),
        "devices": [],
    }

    try:
        import torch
    except Exception as exc:  # pragma: no cover - depends on target environment.
        info.update(
            {
                "torch_import_error": f"{type(exc).__name__}: {exc}",
                "torch_version": None,
                "torch_cuda_version": None,
                "cuda_available": False,
                "cuda_device_count": 0,
            }
        )
        return info

    info.update(
        {
            "torch_version": torch.__version__,
            "torch_cuda_version": torch.version.cuda,
            "cuda_available": torch.cuda.is_available(),
            "cuda_device_count": torch.cuda.device_count(),
        }
    )

    if torch.cuda.is_available():
        for idx in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(idx)
            info["devices"].append(
                {
                    "id": idx,
                    "name": torch.cuda.get_device_name(idx),
                    "capability": torch.cuda.get_device_capability(idx),
                    "total_memory_GB": round(props.total_memory / 1024**3, 2),
                }
            )

    return info


def main() -> int:
    info = collect_env()
    print(json.dumps(info, indent=2, ensure_ascii=False))
    if info.get("torch_import_error"):
        return 2
    return 0 if info.get("cuda_available") else 1


if __name__ == "__main__":
    raise SystemExit(main())

