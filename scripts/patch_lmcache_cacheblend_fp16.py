#!/usr/bin/env python3
"""Make LMCache 0.3.9's RoPE self-test honor the frozen FP16 runtime.

LMCache's validation helper hard-codes BF16 dummy tensors even when vLLM was
started with ``--dtype float16``.  The actual RoPE cache then has FP16 dtype,
so validation aborts before CacheBlend executes.  This reversible patch only
changes the two validation tensors; it does not alter the blend path.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


MARKER = "# CONTRACTKV_LMCACHE_FP16_VALIDATION_V1"
OLD = 'dtype=torch.bfloat16)'
NEW = 'dtype=torch.float16)'


def digest(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--action", choices=("install", "remove", "status"), required=True)
    args = parser.parse_args()
    backup = args.source.with_suffix(args.source.suffix + ".contractkv-original")
    text = args.source.read_text(encoding="utf-8")
    installed = MARKER in text
    if args.action == "status":
        print({"installed": installed, "sha256": digest(text), "backup": str(backup)})
        return 0
    if args.action == "install":
        if not installed:
            count = text.count(OLD)
            if count != 2:
                raise RuntimeError(f"expected exactly two BF16 validation tensors, found {count}")
            if not backup.exists():
                backup.write_text(text, encoding="utf-8")
            text = MARKER + "\n" + text.replace(OLD, NEW)
            args.source.write_text(text, encoding="utf-8")
        print({"installed": True, "sha256": digest(args.source.read_text(encoding="utf-8"))})
        return 0
    if not backup.exists():
        raise FileNotFoundError(f"missing backup: {backup}")
    args.source.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
    print({"installed": False, "sha256": digest(args.source.read_text(encoding="utf-8"))})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
