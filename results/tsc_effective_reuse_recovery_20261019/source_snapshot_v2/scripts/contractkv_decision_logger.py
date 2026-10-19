#!/usr/bin/env python3
"""JSONL decision/request logger for ContractKV runtime prototype."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class DecisionLogger:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, row: dict[str, Any]) -> float:
        started = time.perf_counter()
        payload = {"timestamp": time.time(), **row}
        with self.path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return (time.perf_counter() - started) * 1000
