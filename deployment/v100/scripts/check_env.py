#!/usr/bin/env python3
"""Emit an auditable CUDA and GPU inventory from the active experiment environment."""

import json
import platform

import torch

payload = {
    "python": platform.python_version(),
    "torch": torch.__version__,
    "torch_cuda": torch.version.cuda,
    "cuda_available": torch.cuda.is_available(),
    "cuda_device_count": torch.cuda.device_count(),
    "devices": [],
}

if torch.cuda.is_available():
    for index in range(torch.cuda.device_count()):
        properties = torch.cuda.get_device_properties(index)
        payload["devices"].append(
            {
                "id": index,
                "name": properties.name,
                "capability": list(torch.cuda.get_device_capability(index)),
                "total_memory_gib": round(properties.total_memory / 1024**3, 2),
            }
        )

print(json.dumps(payload, indent=2, sort_keys=True))
