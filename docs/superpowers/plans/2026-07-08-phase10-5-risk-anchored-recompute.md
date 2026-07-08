# Phase 10.5 Risk-Anchored Recompute Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the real Qwen3-8B quality-risk matrix from Phase 10.2B with the real vLLM V1 recompute actuator from Phase 10.4B, and test whether Risk-Anchored Recompute (RAR) improves block headroom, pressure completion, and SLO goodput without quality collapse.

**Architecture:** Phase 10.5 uses a conservative prefix-anchored design: choose an anchor boundary, keep the high-risk contiguous prefix resident, and release/recompute only the suffix. The planner distinguishes text that cannot be dropped from KV residency that can be released and reconstructed; `USER_QUERY` is reconstructable in the suffix, not a reason to reject suffix recompute. Arbitrary middle-segment hole punching and MiniPIC-style stitching are explicitly out of scope for this phase because they violate vLLM's contiguous computed-prefix assumption and belong to a later Phase 11.

**Tech Stack:** Python 3.10, unittest, vLLM 0.10.2 V1 scheduler/KV cache internals, OpenAI-compatible vLLM API, local CSV/JSONL artifacts under `results/hard_systems/`, reports under `docs/`.

---

## File Structure

Create:

- `tests/test_phase10_5_anchor_recompute.py`
  - Tests anchor planner schema, anchor boundary rules, suffix-block accounting, actuator installer reversibility, and policy-eval summary formulas.
- `scripts/build_anchor_residency_plan.py`
  - Reads workload traces and real risk summary, computes segment block spans, chooses anchor boundary, and emits `anchor_residency_plan_v0.jsonl`.
- `scripts/audit_vllm_v1_suffix_free.py`
  - Audits vLLM V1 `kv_cache_manager`, coordinator, and block pool APIs to decide whether suffix-only physical block free is safe enough to probe.
- `scripts/install_vllm_v1_anchor_recompute_probe.py`
  - Installs a guarded vLLM V1 probe for prefix-anchored recompute if the audit opens the gate.
- `scripts/build_anchor_recompute_probe_summary.py`
  - Converts probe events plus request outcomes into `anchored_recompute_poc_v0.csv`.
- `scripts/run_recompute_policy_pressure_eval.py`
  - Runs pressure workloads for `vllm-default`, `full-recompute`, `budget-aware-greedy-recompute`, and `contractkv-anchored-recompute`.
- `scripts/evaluate_recompute_policy_quality.py`
  - Scores outputs using the same scoring primitives as `scripts/run_real_quality_matrix.py`.
- `docs/phase10_5a_anchor_residency_plan_report.md`
- `docs/phase10_5b_anchored_recompute_actuator_report.md`
- `docs/phase10_5c_recompute_policy_pressure_report.md`
- `docs/phase10_5d_recompute_quality_report.md`
- `docs/phase10_5_real_recompute_policy_closeout.md`

Expected outputs:

- `results/hard_systems/anchor_residency_plan_v0.jsonl`
- `results/hard_systems/vllm_v1_suffix_free_audit_v0.json`
- `results/hard_systems/anchored_recompute_events_v0.jsonl`
- `results/hard_systems/anchored_recompute_poc_v0.csv`
- `results/hard_systems/contractkv_recompute_policy_events_v0.jsonl`
- `results/hard_systems/contractkv_recompute_policy_eval_v0.csv`
- `results/hard_systems/contractkv_recompute_quality_eval_v0.csv`

Modify only if needed:

- `scripts/run_real_quality_matrix.py`
  - Reuse scoring helpers. Avoid changing existing Phase 10.2 behavior unless tests force a bug fix.
- `scripts/install_vllm_v1_recompute_probe.py`
  - Keep Phase 10.4B full recompute probe intact as baseline. Do not merge anchored recompute into it.

---

## Phase Gate Summary

Phase 10.5 must proceed through gates:

1. `10.5A`: planner works offline and marks which requests are safe to release.
2. `10.5B-audit`: vLLM V1 suffix-free path is open. If blocked, switch to prefix-cache layout fallback.
3. `10.5B-POC`: retained prefix blocks remain resident, suffix blocks are freed, request completes, and resume is not from token 0.
4. `10.5C`: pressure benchmark compares policies under real vLLM.
5. `10.5D`: real output quality does not collapse.

Do not claim system benefit until `10.5C` and `10.5D` both produce positive evidence.

Supplemental constraints from the Phase 10.5 review:

```text
method name: Risk-Anchored Recompute (RAR)
MUST_RESIDENT_TYPES = {"SYS_PROMPT", "TOOL_SCHEMA"}
MUST_RECONSTRUCT_TYPES = {"USER_QUERY"}
DROP_FORBIDDEN_TYPES = {"SYS_PROMPT", "TOOL_SCHEMA", "USER_QUERY"}
```

RAR is not "dropping low-risk text." It releases suffix KV residency and later reconstructs the suffix from retained text. The anchor optimizer should maximize reclaimed blocks under real quality-risk, recompute-cost, SLO/slack, and boundary-safety constraints:

```text
maximize reclaimed_blocks(anchor)

subject to:
  quality_risk(anchor) <= epsilon
  estimated_recompute_ms(anchor) <= slack_or_SLO_margin
  boundary_safety(anchor) = true
  must_reconstruct_segments are preserved as text
```

Planner records must include:

```text
reclaimed_blocks
estimated_recompute_ms
slack_ms
slo_margin_ms
slack_feasible
anchor_utility = reclaimed_blocks / max(estimated_recompute_ms, 1)
boundary_guard_tokens
recompute_start_token
decision_reason
recomputed_segment_types
dropped_segment_types
```

Runtime POC success must require all invariants:

```text
prefix_blocks_retained_exact
suffix_blocks_freed_exact
free_gpu_blocks_delta >= suffix_blocks_freed
request.num_computed_tokens_after == anchor_token_end
request_completed
response non-empty
```

Pressure evaluation must report:

```text
mean_block_headroom_gain
total_recompute_tokens_saved_vs_full
capacity_failures
completion_lift_vs_default
slo_goodput_delta_vs_default
```

These supplemental constraints override any older code snippet below that treats `USER_QUERY` as a suffix-release blocker or describes the action as dropping `released_segment_types`. Implementation should use `recomputed_segment_types` and `dropped_segment_types`; suffix text is preserved and reconstructed.

---

### Task 1: Anchor Residency Planner Tests

**Files:**

- Create: `tests/test_phase10_5_anchor_recompute.py`
- Create: `scripts/build_anchor_residency_plan.py`

- [ ] **Step 1: Write failing tests for anchor boundary and schema**

Create `tests/test_phase10_5_anchor_recompute.py` with:

```python
import unittest

from scripts.build_anchor_residency_plan import (
    choose_anchor_boundary,
    compute_segment_block_span,
    make_anchor_residency_record,
)


class Phase105AnchorPlannerTests(unittest.TestCase):
    def sample_segments(self):
        return [
            {"type": "SYS_PROMPT", "text": "system", "token_count": 64},
            {"type": "RAG_CHUNK", "text": "evidence", "token_count": 896},
            {"type": "CHAT_HISTORY", "text": "history", "token_count": 2048},
            {"type": "SCRATCHPAD", "text": "scratch", "token_count": 1024},
            {"type": "USER_QUERY", "text": "question", "token_count": 64},
        ]

    def test_compute_segment_block_span_uses_block_size_16(self):
        span = compute_segment_block_span(token_start=64, token_count=32, block_size=16)
        self.assertEqual(span["logical_block_start"], 4)
        self.assertEqual(span["logical_block_end"], 6)
        self.assertEqual(span["block_count"], 2)

    def test_anchor_boundary_keeps_high_risk_prefix_and_releases_suffix(self):
        risks = {
            "SYS_PROMPT": 1.0,
            "RAG_CHUNK": 0.45,
            "CHAT_HISTORY": 0.02,
            "SCRATCHPAD": 0.01,
            "USER_QUERY": 1.0,
        }
        decision = choose_anchor_boundary(
            segments=self.sample_segments(),
            risk_by_segment_type=risks,
            block_size=16,
            risk_threshold=0.05,
            min_suffix_blocks=64,
        )

        self.assertEqual(decision["residency_decision"], "release_suffix_candidate")
        self.assertEqual(decision["anchor_segment_index"], 1)
        self.assertGreaterEqual(decision["suffix_blocks_releasable"], 64)
        self.assertIn("CHAT_HISTORY", decision["released_segment_types"])
        self.assertNotIn("USER_QUERY", decision["released_segment_types"])

    def test_anchor_boundary_refuses_when_suffix_contains_query(self):
        segments = [
            {"type": "SYS_PROMPT", "text": "system", "token_count": 64},
            {"type": "USER_QUERY", "text": "question", "token_count": 64},
        ]
        decision = choose_anchor_boundary(
            segments=segments,
            risk_by_segment_type={"SYS_PROMPT": 1.0, "USER_QUERY": 1.0},
            block_size=16,
            risk_threshold=0.05,
            min_suffix_blocks=1,
        )

        self.assertEqual(decision["residency_decision"], "keep_full_request")
        self.assertEqual(decision["suffix_blocks_releasable"], 0)

    def test_anchor_residency_record_has_required_fields(self):
        record = make_anchor_residency_record(
            trace_id="trace-1",
            request_id="req-1",
            dataset="LongBench",
            task="hotpotqa",
            segments=self.sample_segments(),
            risk_by_segment_type={"SYS_PROMPT": 1.0, "RAG_CHUNK": 0.5, "CHAT_HISTORY": 0.01, "SCRATCHPAD": 0.01, "USER_QUERY": 1.0},
            block_size=16,
        )

        for field in [
            "trace_id",
            "request_id",
            "dataset",
            "task",
            "block_size",
            "anchor_token_end",
            "anchor_block_end",
            "suffix_blocks_releasable",
            "estimated_recompute_tokens",
            "estimated_quality_risk",
            "residency_decision",
            "segments",
        ]:
            self.assertIn(field, record)
        self.assertGreater(len(record["segments"]), 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m unittest tests.test_phase10_5_anchor_recompute -v
```

Expected:

```text
ModuleNotFoundError: No module named 'scripts.build_anchor_residency_plan'
```

---

### Task 2: Anchor Residency Planner Implementation

**Files:**

- Create: `scripts/build_anchor_residency_plan.py`
- Test: `tests/test_phase10_5_anchor_recompute.py`

- [ ] **Step 1: Implement planner functions**

Create `scripts/build_anchor_residency_plan.py`:

```python
#!/usr/bin/env python3
"""Build prefix-anchor/suffix-recompute residency plans for Phase 10.5."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


PINNED_SEGMENT_TYPES = {"SYS_PROMPT", "TOOL_SCHEMA", "USER_QUERY"}
LOW_RISK_DEFAULT = 0.01
HIGH_RISK_DEFAULT = 1.0


def compute_segment_block_span(token_start: int, token_count: int, block_size: int) -> dict[str, int]:
    token_end = token_start + token_count
    return {
        "token_start": token_start,
        "token_end": token_end,
        "logical_block_start": token_start // block_size,
        "logical_block_end": (token_end + block_size - 1) // block_size,
        "block_count": ((token_end + block_size - 1) // block_size) - (token_start // block_size),
    }


def segment_risk(segment: dict[str, Any], risk_by_segment_type: dict[str, float]) -> float:
    seg_type = str(segment.get("type", "UNKNOWN"))
    if seg_type in PINNED_SEGMENT_TYPES:
        return HIGH_RISK_DEFAULT
    return float(risk_by_segment_type.get(seg_type, LOW_RISK_DEFAULT))


def annotate_segments(segments: list[dict[str, Any]], risk_by_segment_type: dict[str, float], block_size: int) -> list[dict[str, Any]]:
    annotated = []
    cursor = 0
    for index, segment in enumerate(segments):
        token_count = int(segment.get("token_count") or 0)
        span = compute_segment_block_span(cursor, token_count, block_size)
        row = dict(segment)
        row.update(span)
        row["segment_id"] = row.get("segment_id", f"seg-{index}")
        row["real_quality_risk"] = segment_risk(row, risk_by_segment_type)
        row["pinned"] = row["type"] in PINNED_SEGMENT_TYPES
        annotated.append(row)
        cursor += token_count
    return annotated


def choose_anchor_boundary(
    segments: list[dict[str, Any]],
    risk_by_segment_type: dict[str, float],
    block_size: int = 16,
    risk_threshold: float = 0.05,
    min_suffix_blocks: int = 64,
) -> dict[str, Any]:
    annotated = annotate_segments(segments, risk_by_segment_type, block_size)
    if not annotated:
        return {
            "residency_decision": "keep_full_request",
            "anchor_segment_index": -1,
            "anchor_token_end": 0,
            "anchor_block_end": 0,
            "suffix_blocks_releasable": 0,
            "estimated_recompute_tokens": 0,
            "estimated_quality_risk": 0.0,
            "released_segment_types": [],
        }

    best = None
    for anchor_index in range(len(annotated)):
        suffix = annotated[anchor_index + 1 :]
        if not suffix:
            continue
        if any(item["type"] in PINNED_SEGMENT_TYPES for item in suffix):
            continue
        suffix_blocks = sum(int(item["block_count"]) for item in suffix)
        suffix_tokens = sum(int(item["token_count"]) for item in suffix)
        suffix_risk = max(float(item["real_quality_risk"]) for item in suffix)
        if suffix_blocks < min_suffix_blocks or suffix_risk > risk_threshold:
            continue
        candidate = {
            "residency_decision": "release_suffix_candidate",
            "anchor_segment_index": anchor_index,
            "anchor_token_end": int(annotated[anchor_index]["token_end"]),
            "anchor_block_end": int(annotated[anchor_index]["logical_block_end"]),
            "suffix_blocks_releasable": suffix_blocks,
            "estimated_recompute_tokens": suffix_tokens,
            "estimated_quality_risk": suffix_risk,
            "released_segment_types": sorted({str(item["type"]) for item in suffix}),
        }
        if best is None or candidate["suffix_blocks_releasable"] > best["suffix_blocks_releasable"]:
            best = candidate

    if best is not None:
        return best
    last = annotated[-1]
    return {
        "residency_decision": "keep_full_request",
        "anchor_segment_index": len(annotated) - 1,
        "anchor_token_end": int(last["token_end"]),
        "anchor_block_end": int(last["logical_block_end"]),
        "suffix_blocks_releasable": 0,
        "estimated_recompute_tokens": 0,
        "estimated_quality_risk": max(float(item["real_quality_risk"]) for item in annotated),
        "released_segment_types": [],
    }


def make_anchor_residency_record(
    trace_id: str,
    request_id: str,
    dataset: str,
    task: str,
    segments: list[dict[str, Any]],
    risk_by_segment_type: dict[str, float],
    block_size: int = 16,
) -> dict[str, Any]:
    annotated = annotate_segments(segments, risk_by_segment_type, block_size)
    decision = choose_anchor_boundary(segments, risk_by_segment_type, block_size)
    return {
        "trace_id": trace_id,
        "request_id": request_id,
        "dataset": dataset,
        "task": task,
        "block_size": block_size,
        "anchor_token_end": decision["anchor_token_end"],
        "anchor_block_end": decision["anchor_block_end"],
        "suffix_blocks_releasable": decision["suffix_blocks_releasable"],
        "estimated_recompute_tokens": decision["estimated_recompute_tokens"],
        "estimated_quality_risk": decision["estimated_quality_risk"],
        "residency_decision": decision["residency_decision"],
        "released_segment_types": decision["released_segment_types"],
        "segments": annotated,
    }
```

- [ ] **Step 2: Add CLI to write JSONL**

Append:

```python
def load_risk_by_segment_type(path: Path) -> dict[str, float]:
    risks = {}
    if not path.exists():
        return risks
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            condition = row.get("condition", "")
            if condition not in {"segment_eviction", "context_truncation"}:
                continue
            dataset = row.get("dataset", "")
            risk = float(row.get("mean_quality_drop") or 0.0)
            if dataset == "RepoBench":
                risks["REPO_CONTEXT"] = max(risks.get("REPO_CONTEXT", 0.0), risk)
            elif dataset == "LongBench":
                risks["RAG_CHUNK"] = max(risks.get("RAG_CHUNK", 0.0), risk)
            elif dataset == "RULER":
                risks["SYNTHETIC_CONTEXT"] = max(risks.get("SYNTHETIC_CONTEXT", 0.0), risk)
    risks.setdefault("CHAT_HISTORY", 0.01)
    risks.setdefault("SCRATCHPAD", 0.01)
    return risks


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--traces", type=Path, default=Path("results/workload/agent_trace_v0.jsonl"))
    parser.add_argument("--risk-summary", type=Path, default=Path("results/hard_systems/real_quality_risk_summary_qwen3_8b_v0.csv"))
    parser.add_argument("--output", type=Path, default=Path("results/hard_systems/anchor_residency_plan_v0.jsonl"))
    parser.add_argument("--block-size", type=int, default=16)
    args = parser.parse_args()
    risk_by_segment_type = load_risk_by_segment_type(args.risk_summary)
    rows = []
    for index, trace in enumerate(load_jsonl(args.traces)):
        rows.append(
            make_anchor_residency_record(
                trace_id=str(trace.get("trace_id", index)),
                request_id=str(trace.get("request_id", trace.get("trace_id", index))),
                dataset=str(trace.get("dataset", "")),
                task=str(trace.get("task", "")),
                segments=list(trace.get("segments", [])),
                risk_by_segment_type=risk_by_segment_type,
                block_size=args.block_size,
            )
        )
    write_jsonl(args.output, rows)
    print(f"anchor_plan_rows={len(rows)}")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run tests**

Run:

```powershell
python -m unittest tests.test_phase10_5_anchor_recompute -v
```

Expected:

```text
Ran 4 tests
OK
```

- [ ] **Step 4: Generate planner output**

Run:

```powershell
python scripts/build_anchor_residency_plan.py --traces results/workload/agent_trace_v0.jsonl --risk-summary results/hard_systems/real_quality_risk_summary_qwen3_8b_v0.csv --output results/hard_systems/anchor_residency_plan_v0.jsonl
```

Expected:

```text
anchor_plan_rows=140
```

- [ ] **Step 5: Commit Task 1-2**

Run:

```powershell
git add tests/test_phase10_5_anchor_recompute.py scripts/build_anchor_residency_plan.py results/hard_systems/anchor_residency_plan_v0.jsonl
git commit -m "Add Phase 10.5 anchor residency planner"
```

---

### Task 3: Suffix-Free Feasibility Audit

**Files:**

- Modify: `tests/test_phase10_5_anchor_recompute.py`
- Create: `scripts/audit_vllm_v1_suffix_free.py`
- Output: `results/hard_systems/vllm_v1_suffix_free_audit_v0.json`

- [ ] **Step 1: Add failing tests for suffix-free audit schema**

Append to `tests/test_phase10_5_anchor_recompute.py`:

```python
from scripts.audit_vllm_v1_suffix_free import audit_suffix_free_path


class Phase105SuffixFreeAuditTests(unittest.TestCase):
    def test_suffix_free_audit_reports_gate_and_required_files(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "v1" / "core").mkdir(parents=True)
            (root / "v1" / "core" / "kv_cache_manager.py").write_text(
                "def get_block_ids(self, request_id): pass\n"
                "def free(self, request): self.coordinator.free(request.request_id)\n"
                "def cache_blocks(self, request, num_computed_tokens): pass\n",
                encoding="utf-8",
            )
            (root / "v1" / "core" / "block_pool.py").write_text(
                "def get_num_free_blocks(self): pass\n"
                "def free_block(self, block): pass\n",
                encoding="utf-8",
            )
            report = audit_suffix_free_path(root)

        self.assertEqual(report["schema_version"], "phase10_5_suffix_free_audit_v0")
        self.assertIn(report["suffix_free_gate"], {"open_for_probe", "blocked"})
        self.assertIn("v1/core/kv_cache_manager.py", report["files"])
        self.assertIn("minimum_probe", report)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m unittest tests.test_phase10_5_anchor_recompute.Phase105SuffixFreeAuditTests -v
```

Expected:

```text
ModuleNotFoundError: No module named 'scripts.audit_vllm_v1_suffix_free'
```

- [ ] **Step 3: Implement audit script**

Create `scripts/audit_vllm_v1_suffix_free.py`:

```python
#!/usr/bin/env python3
"""Audit whether vLLM V1 can safely probe suffix-only KV block release."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import sys
from pathlib import Path


FOCUS_FILES = [
    "v1/core/kv_cache_manager.py",
    "v1/core/block_pool.py",
    "v1/core/sched/scheduler.py",
]


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except FileNotFoundError:
        return ""


def audit_suffix_free_path(vllm_root: Path) -> dict:
    files = {}
    for rel in FOCUS_FILES:
        text = read(vllm_root / rel)
        files[rel] = {
            "exists": bool(text),
            "has_get_block_ids": "get_block_ids" in text,
            "has_request_free": "def free(" in text or ".free(" in text,
            "has_block_pool_free": "free_block" in text or "free_blocks" in text or "free(" in text,
            "has_num_computed_tokens": "num_computed_tokens" in text,
        }
    kv = files["v1/core/kv_cache_manager.py"]
    pool = files["v1/core/block_pool.py"]
    sched = files["v1/core/sched/scheduler.py"]
    open_for_probe = (
        kv["has_get_block_ids"]
        and kv["has_request_free"]
        and pool["has_block_pool_free"]
        and sched["has_num_computed_tokens"]
    )
    return {
        "schema_version": "phase10_5_suffix_free_audit_v0",
        "files": files,
        "suffix_free_gate": "open_for_probe" if open_for_probe else "blocked",
        "minimum_probe": (
            "Install guarded suffix-free probe that retains logical blocks below anchor_block_end, frees suffix blocks, "
            "sets request.num_computed_tokens to anchor_tokens, and verifies request completion."
            if open_for_probe
            else "Do not patch vLLM; use prefix-cache canonical layout fallback."
        ),
    }


def import_vllm_info() -> tuple[Path, str]:
    import vllm

    return Path(vllm.__file__).resolve().parent, importlib.metadata.version("vllm")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vllm-root", type=Path)
    parser.add_argument("--output", type=Path, default=Path("results/hard_systems/vllm_v1_suffix_free_audit_v0.json"))
    args = parser.parse_args()
    if args.vllm_root:
        root = args.vllm_root
        version = "unknown"
    else:
        root, version = import_vllm_info()
    report = audit_suffix_free_path(root)
    report["vllm_root"] = str(root)
    report["vllm_version"] = version
    report["python_executable"] = sys.executable
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"suffix_free_gate": report["suffix_free_gate"], "vllm_version": version}, sort_keys=True))
    return 0 if report["suffix_free_gate"] == "open_for_probe" else 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run local tests**

Run:

```powershell
python -m unittest tests.test_phase10_5_anchor_recompute -v
```

Expected:

```text
OK
```

- [ ] **Step 5: Run audit on server**

Upload and run:

```powershell
& 'E:\PuTTy\pscp.exe' -batch -pw '12345678' -hostkey 'SHA256:hRNlxitqGzUJog3+HuGNgzd37IF62CQQXq/swz4us7M' .\scripts\audit_vllm_v1_suffix_free.py user@10.15.0.47:/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv/scripts/audit_vllm_v1_suffix_free.py
& 'E:\PuTTy\plink.exe' -ssh -batch -pw '12345678' -hostkey 'SHA256:hRNlxitqGzUJog3+HuGNgzd37IF62CQQXq/swz4us7M' user@10.15.0.47 'cd /media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv && source /home/user/miniconda3/etc/profile.d/conda.sh && conda activate contractkv-cu128 && python scripts/audit_vllm_v1_suffix_free.py --output results/hard_systems/vllm_v1_suffix_free_audit_v0.json'
& 'E:\PuTTy\pscp.exe' -batch -pw '12345678' -hostkey 'SHA256:hRNlxitqGzUJog3+HuGNgzd37IF62CQQXq/swz4us7M' user@10.15.0.47:/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv/results/hard_systems/vllm_v1_suffix_free_audit_v0.json .\results\hard_systems\vllm_v1_suffix_free_audit_v0.json
```

Expected:

```text
{"suffix_free_gate": "open_for_probe", "vllm_version": "0.10.2"}
```

If output is `blocked`, do not implement Task 4. Jump to Task 9 prefix-cache fallback.

---

### Task 4: Anchored Recompute Probe Installer

**Files:**

- Modify: `tests/test_phase10_5_anchor_recompute.py`
- Create: `scripts/install_vllm_v1_anchor_recompute_probe.py`
- Create: `scripts/build_anchor_recompute_probe_summary.py`

- [ ] **Step 1: Add failing tests for guarded installer and summary**

Append:

```python
from scripts.install_vllm_v1_anchor_recompute_probe import install as install_anchor_probe
from scripts.install_vllm_v1_anchor_recompute_probe import uninstall as uninstall_anchor_probe
from scripts.build_anchor_recompute_probe_summary import summarize_anchor_probe


class Phase105AnchoredProbeTests(unittest.TestCase):
    def test_anchor_probe_installer_is_guarded_and_reversible(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            scheduler = Path(tmp) / "scheduler.py"
            original = (
                "class Scheduler:\n"
                "    def schedule(self) -> SchedulerOutput:\n"
                "        scheduled_timestamp = time.monotonic()\n"
                "        # First, schedule the RUNNING requests.\n"
                "        return SchedulerOutput()\n"
            )
            scheduler.write_text(original, encoding="utf-8")
            self.assertEqual(install_anchor_probe(scheduler), "installed")
            patched = scheduler.read_text(encoding="utf-8")
            self.assertIn("CONTRACTKV_ANCHOR_RECOMPUTE_PROBE", patched)
            self.assertIn("anchor_token_end", patched)
            self.assertEqual(uninstall_anchor_probe(scheduler), "uninstalled")
            self.assertEqual(scheduler.read_text(encoding="utf-8"), original)

    def test_anchor_probe_summary_requires_prefix_retained_suffix_freed_and_completion(self):
        events = [{
            "event": "contractkv_anchor_recompute",
            "request_id": "req-1",
            "anchor_token_end": 1024,
            "before_free_gpu_blocks": 100,
            "after_free_gpu_blocks": 164,
            "suffix_blocks_freed": 64,
            "prefix_blocks_retained": 64,
            "num_computed_tokens_after": 1024,
        }]
        requests = [{"success": True, "latency_ms": 200.0, "response_bytes": 512}]
        row = summarize_anchor_probe(events, requests, "qwen3-4b")

        self.assertTrue(row["anchored_recompute_success"])
        self.assertEqual(row["suffix_blocks_freed"], 64)
        self.assertEqual(row["num_computed_tokens_after"], 1024)
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m unittest tests.test_phase10_5_anchor_recompute.Phase105AnchoredProbeTests -v
```

Expected:

```text
ModuleNotFoundError: No module named 'scripts.install_vllm_v1_anchor_recompute_probe'
```

- [ ] **Step 3: Implement installer with a conservative gate**

Create `scripts/install_vllm_v1_anchor_recompute_probe.py`.

Implementation requirements:

- It must create backup `scheduler.py.contractkv_anchor_recompute_probe.bak`.
- It must only activate when `CONTRACTKV_ANCHOR_RECOMPUTE_PROBE=1`.
- It must read `CONTRACTKV_ANCHOR_TOKEN_END`.
- It must log to `CONTRACTKV_ANCHOR_RECOMPUTE_PROBE_LOG`.
- It must refuse to run if `anchor_token_end <= 0`.
- It must not modify behavior when env var is unset.

Minimum code shape:

```python
MARKER_BEGIN = "# CONTRACTKV_ANCHOR_RECOMPUTE_PROBE_BEGIN"
MARKER_END = "# CONTRACTKV_ANCHOR_RECOMPUTE_PROBE_END"
BACKUP_SUFFIX = ".contractkv_anchor_recompute_probe.bak"
```

The injected helper must use the same real vLLM fields proven in Phase 10.4B:

```python
selected.status = RequestStatus.PREEMPTED
selected.num_computed_tokens = anchor_token_end
scheduler.waiting.prepend_request(selected)
```

For the first implementation, if true suffix-only physical block free cannot be called safely, the helper must write:

```json
{"anchored_gate": "blocked_before_physical_suffix_free"}
```

and return without changing vLLM state. This is a safety gate, not a failure.

- [ ] **Step 4: Implement summary builder**

Create `scripts/build_anchor_recompute_probe_summary.py`:

```python
#!/usr/bin/env python3
"""Summarize Phase 10.5B anchored recompute POC events."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


FIELDS = [
    "model",
    "anchored_recompute_success",
    "request_completed",
    "anchor_token_end",
    "prefix_blocks_retained",
    "suffix_blocks_freed",
    "free_gpu_blocks_delta",
    "num_computed_tokens_after",
    "request_latency_ms",
    "response_bytes",
    "notes",
]


def summarize_anchor_probe(events: list[dict[str, Any]], requests: list[dict[str, Any]], model: str) -> dict[str, Any]:
    event = next((row for row in events if row.get("event") == "contractkv_anchor_recompute"), {})
    request_completed = any(bool(row.get("success")) for row in requests)
    response_bytes = max([int(row.get("response_bytes") or 0) for row in requests] or [0])
    request_latency_ms = max([float(row.get("latency_ms") or 0.0) for row in requests] or [0.0])
    suffix_blocks_freed = int(event.get("suffix_blocks_freed") or 0)
    prefix_blocks_retained = int(event.get("prefix_blocks_retained") or 0)
    anchor_token_end = int(event.get("anchor_token_end") or 0)
    num_computed_tokens_after = int(event.get("num_computed_tokens_after") or 0)
    delta = int(event.get("after_free_gpu_blocks") or 0) - int(event.get("before_free_gpu_blocks") or 0)
    success = (
        request_completed
        and suffix_blocks_freed > 0
        and prefix_blocks_retained > 0
        and num_computed_tokens_after == anchor_token_end
        and response_bytes > 0
    )
    return {
        "model": model,
        "anchored_recompute_success": success,
        "request_completed": request_completed,
        "anchor_token_end": anchor_token_end,
        "prefix_blocks_retained": prefix_blocks_retained,
        "suffix_blocks_freed": suffix_blocks_freed,
        "free_gpu_blocks_delta": delta,
        "num_computed_tokens_after": num_computed_tokens_after,
        "request_latency_ms": request_latency_ms,
        "response_bytes": response_bytes,
        "notes": "anchored_suffix_recompute_success" if success else "anchored_probe_incomplete",
    }
```

Add CLI following the pattern in `scripts/build_recompute_actuator_probe_summary.py`.

- [ ] **Step 5: Run tests**

Run:

```powershell
python -m unittest tests.test_phase10_5_anchor_recompute -v
```

Expected:

```text
OK
```

---

### Task 5: Server Anchored Recompute POC

**Files:**

- Output: `results/hard_systems/anchored_recompute_events_v0.jsonl`
- Output: `results/hard_systems/anchored_recompute_poc_v0.csv`
- Report: `docs/phase10_5b_anchored_recompute_actuator_report.md`

- [ ] **Step 1: Upload scripts and install guarded patch**

Run:

```powershell
& 'E:\PuTTy\pscp.exe' -batch -pw '12345678' -hostkey 'SHA256:hRNlxitqGzUJog3+HuGNgzd37IF62CQQXq/swz4us7M' .\scripts\install_vllm_v1_anchor_recompute_probe.py user@10.15.0.47:/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv/scripts/install_vllm_v1_anchor_recompute_probe.py
& 'E:\PuTTy\plink.exe' -ssh -batch -pw '12345678' -hostkey 'SHA256:hRNlxitqGzUJog3+HuGNgzd37IF62CQQXq/swz4us7M' user@10.15.0.47 'cd /media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv && source /home/user/miniconda3/etc/profile.d/conda.sh && conda activate contractkv-cu128 && python scripts/install_vllm_v1_anchor_recompute_probe.py --scheduler /home/user/miniconda3/envs/contractkv-cu128/lib/python3.10/site-packages/vllm/v1/core/sched/scheduler.py --action install && python -m py_compile /home/user/miniconda3/envs/contractkv-cu128/lib/python3.10/site-packages/vllm/v1/core/sched/scheduler.py'
```

Expected:

```text
installed
```

- [ ] **Step 2: Run Qwen3-4B anchored POC**

Use a single request first:

```bash
CONTRACTKV_ANCHOR_RECOMPUTE_PROBE=1
CONTRACTKV_ANCHOR_TOKEN_END=1024
CONTRACTKV_ANCHOR_RECOMPUTE_PROBE_LOG=results/hard_systems/anchored_recompute_events_v0.jsonl
```

Start server with Qwen3-4B and send one long request using `scripts/send_concurrent_probe_requests.py`.

Expected success row:

```text
anchored_recompute_success=True
suffix_blocks_freed > 0
prefix_blocks_retained > 0
num_computed_tokens_after == anchor_token_end
request_completed=True
```

- [ ] **Step 3: Run Qwen3-8B anchored POC if Qwen3-4B succeeds**

Use:

```text
model: Qwen3-8B
max_model_len: 8192
max_num_seqs: 2
gpu_memory_utilization: 0.88
```

Expected same success fields as Qwen3-4B.

- [ ] **Step 4: Pull outputs**

Run:

```powershell
& 'E:\PuTTy\pscp.exe' -batch -pw '12345678' -hostkey 'SHA256:hRNlxitqGzUJog3+HuGNgzd37IF62CQQXq/swz4us7M' user@10.15.0.47:/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv/results/hard_systems/anchored_recompute_events_v0.jsonl .\results\hard_systems\anchored_recompute_events_v0.jsonl
& 'E:\PuTTy\pscp.exe' -batch -pw '12345678' -hostkey 'SHA256:hRNlxitqGzUJog3+HuGNgzd37IF62CQQXq/swz4us7M' user@10.15.0.47:/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv/results/hard_systems/anchored_recompute_poc_v0.csv .\results\hard_systems\anchored_recompute_poc_v0.csv
```

- [ ] **Step 5: Write report**

Create `docs/phase10_5b_anchored_recompute_actuator_report.md` with sections:

```markdown
# Phase 10.5B Anchored Recompute Actuator Report

## Goal
## Gate From 10.5A
## vLLM Patch
## Qwen3-4B Result
## Qwen3-8B Result
## Success Criteria
## Limitations
## Decision For 10.5C
```

- [ ] **Step 6: Commit**

Run:

```powershell
git add scripts/install_vllm_v1_anchor_recompute_probe.py scripts/build_anchor_recompute_probe_summary.py results/hard_systems/anchored_recompute_events_v0.jsonl results/hard_systems/anchored_recompute_poc_v0.csv docs/phase10_5b_anchored_recompute_actuator_report.md tests/test_phase10_5_anchor_recompute.py
git commit -m "Add anchored recompute actuator POC"
```

---

### Task 6: Pressure Policy Evaluation

**Files:**

- Modify: `tests/test_phase10_5_anchor_recompute.py`
- Create: `scripts/run_recompute_policy_pressure_eval.py`
- Output: `results/hard_systems/contractkv_recompute_policy_events_v0.jsonl`
- Output: `results/hard_systems/contractkv_recompute_policy_eval_v0.csv`
- Report: `docs/phase10_5c_recompute_policy_pressure_report.md`

- [ ] **Step 1: Add tests for policy metric aggregation**

Append:

```python
from scripts.run_recompute_policy_pressure_eval import aggregate_pressure_metrics


class Phase105PressureEvalTests(unittest.TestCase):
    def test_aggregate_pressure_metrics_reports_goodput_and_block_delta(self):
        rows = [
            {"policy": "contractkv-anchored-recompute", "completed": True, "slo_violation": False, "latency_ms": 100.0, "blocks_freed": 64},
            {"policy": "contractkv-anchored-recompute", "completed": True, "slo_violation": True, "latency_ms": 300.0, "blocks_freed": 32},
            {"policy": "vllm-default", "completed": False, "slo_violation": True, "latency_ms": 0.0, "blocks_freed": 0},
        ]
        summary = aggregate_pressure_metrics(rows, duration_sec=2.0)
        by_policy = {row["policy"]: row for row in summary}

        self.assertEqual(by_policy["contractkv-anchored-recompute"]["completed_requests"], 2)
        self.assertEqual(by_policy["contractkv-anchored-recompute"]["slo_compliant_requests"], 1)
        self.assertEqual(by_policy["contractkv-anchored-recompute"]["slo_compliant_req_per_sec"], 0.5)
        self.assertEqual(by_policy["contractkv-anchored-recompute"]["total_blocks_freed"], 96)
```

- [ ] **Step 2: Implement aggregation and runner skeleton**

Create `scripts/run_recompute_policy_pressure_eval.py`.

Policies:

```python
POLICIES = [
    "vllm-default",
    "full-recompute",
    "budget-aware-greedy-recompute",
    "contractkv-anchored-recompute",
]
```

Aggregator:

```python
def aggregate_pressure_metrics(rows: list[dict], duration_sec: float) -> list[dict]:
    grouped = {}
    for row in rows:
        grouped.setdefault(row["policy"], []).append(row)
    summaries = []
    for policy, items in grouped.items():
        completed = [item for item in items if bool(item.get("completed"))]
        slo_ok = [item for item in completed if not bool(item.get("slo_violation"))]
        summaries.append({
            "policy": policy,
            "attempted_requests": len(items),
            "completed_requests": len(completed),
            "slo_compliant_requests": len(slo_ok),
            "completion_rate": len(completed) / len(items) if items else 0.0,
            "slo_compliant_req_per_sec": len(slo_ok) / duration_sec if duration_sec > 0 else 0.0,
            "total_blocks_freed": sum(int(item.get("blocks_freed") or 0) for item in items),
        })
    return summaries
```

Runner must record:

```text
policy
dataset
trace_id
model
configured_max_model_len
max_num_seqs
completed
slo_violation
latency_ms
ttft_ms
tpot_ms
blocks_freed
free_gpu_blocks_before
free_gpu_blocks_after
recompute_events
error_type
error_message
```

- [ ] **Step 3: Run tests**

Run:

```powershell
python -m unittest tests.test_phase10_5_anchor_recompute.Phase105PressureEvalTests -v
```

Expected:

```text
OK
```

- [ ] **Step 4: Execute pressure eval in two tiers**

Tier 1 debug:

```text
model: Qwen3-4B
max_model_len: 8192
max_num_seqs: 8
sample_count: 20
```

Tier 2 primary:

```text
model: Qwen3-8B
max_model_len: 8192
max_num_seqs: 2
sample_count: 20
```

Only expand to 16K/32K after both tiers complete without server instability.

- [ ] **Step 5: Write report**

Create `docs/phase10_5c_recompute_policy_pressure_report.md`.

Required conclusion fields:

```text
Does ContractKV release real GPU KV blocks under pressure?
Does it complete/admit more requests than vLLM-default?
Does it improve SLO-compliant req/s by at least 10%?
Does full-recompute suffer avoidable latency compared with anchored recompute?
```

- [ ] **Step 6: Commit**

Run:

```powershell
git add scripts/run_recompute_policy_pressure_eval.py results/hard_systems/contractkv_recompute_policy_events_v0.jsonl results/hard_systems/contractkv_recompute_policy_eval_v0.csv docs/phase10_5c_recompute_policy_pressure_report.md tests/test_phase10_5_anchor_recompute.py
git commit -m "Evaluate recompute policies under KV pressure"
```

---

### Task 7: Real Output Quality Check

**Files:**

- Modify: `tests/test_phase10_5_anchor_recompute.py`
- Create: `scripts/evaluate_recompute_policy_quality.py`
- Output: `results/hard_systems/contractkv_recompute_quality_eval_v0.csv`
- Report: `docs/phase10_5d_recompute_quality_report.md`

- [ ] **Step 1: Add tests for quality-drop comparison**

Append:

```python
from scripts.evaluate_recompute_policy_quality import compute_policy_quality_summary


class Phase105QualityEvalTests(unittest.TestCase):
    def test_quality_summary_computes_drop_from_default_baseline(self):
        rows = [
            {"policy": "vllm-default", "dataset": "RULER", "score": 1.0},
            {"policy": "contractkv-anchored-recompute", "dataset": "RULER", "score": 0.98},
            {"policy": "naive-recompute", "dataset": "RULER", "score": 0.80},
        ]
        summary = compute_policy_quality_summary(rows)
        by_policy = {row["policy"]: row for row in summary}

        self.assertAlmostEqual(by_policy["contractkv-anchored-recompute"]["quality_drop"], 0.02)
        self.assertAlmostEqual(by_policy["naive-recompute"]["quality_drop"], 0.20)
```

- [ ] **Step 2: Implement quality summary**

Create `scripts/evaluate_recompute_policy_quality.py`:

```python
#!/usr/bin/env python3
"""Evaluate real output quality for Phase 10.5 recompute policies."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


FIELDS = ["policy", "dataset", "num_samples", "mean_score", "baseline_mean_score", "quality_drop"]


def compute_policy_quality_summary(rows: list[dict]) -> list[dict]:
    grouped = {}
    for row in rows:
        grouped.setdefault((row["policy"], row["dataset"]), []).append(float(row["score"]))
    baseline_by_dataset = {}
    for (policy, dataset), scores in grouped.items():
        if policy == "vllm-default":
            baseline_by_dataset[dataset] = sum(scores) / len(scores)
    out = []
    for (policy, dataset), scores in sorted(grouped.items()):
        mean_score = sum(scores) / len(scores)
        baseline = baseline_by_dataset.get(dataset, mean_score)
        out.append({
            "policy": policy,
            "dataset": dataset,
            "num_samples": len(scores),
            "mean_score": round(mean_score, 6),
            "baseline_mean_score": round(baseline, 6),
            "quality_drop": round(max(0.0, baseline - mean_score), 6),
        })
    return out
```

Add CSV load/write CLI.

- [ ] **Step 3: Run tests**

Run:

```powershell
python -m unittest tests.test_phase10_5_anchor_recompute.Phase105QualityEvalTests -v
```

Expected:

```text
OK
```

- [ ] **Step 4: Evaluate quality**

Minimum sample set:

```text
RULER: 20
LongBench hotpotqa/qasper 32K-safe subset: 20
RepoBench: 20
```

Use the same scoring approach as `scripts/run_real_quality_matrix.py`.

Success threshold:

```text
ContractKV-anchored-recompute quality_drop <= 0.03
ContractKV-anchored-recompute quality_drop < naive-recompute quality_drop
```

- [ ] **Step 5: Write report**

Create `docs/phase10_5d_recompute_quality_report.md`.

Required sections:

```markdown
# Phase 10.5D Recompute Quality Report

## Inputs
## Policies
## Dataset Subsets
## Quality Results
## Capacity Failures
## Scoring Artifact Risks
## Decision
```

- [ ] **Step 6: Commit**

Run:

```powershell
git add scripts/evaluate_recompute_policy_quality.py results/hard_systems/contractkv_recompute_quality_eval_v0.csv docs/phase10_5d_recompute_quality_report.md tests/test_phase10_5_anchor_recompute.py
git commit -m "Evaluate quality for anchored recompute policies"
```

---

### Task 8: Phase 10.5 Closeout

**Files:**

- Create: `docs/phase10_5_real_recompute_policy_closeout.md`

- [ ] **Step 1: Write closeout**

Create:

```markdown
# Phase 10.5 Real Recompute Policy Closeout

## Goal

Connect real risk with real vLLM V1 recompute/residency control.

## Inputs

- Phase 10.2B real quality risk
- Phase 10.4B real recompute actuator
- Phase 10.5A anchor residency plans
- Phase 10.5B anchored recompute POC
- Phase 10.5C pressure metrics
- Phase 10.5D quality metrics

## Main Finding

State one of:

1. `success_system_benefit`: anchored recompute improves pressure handling or SLO goodput with acceptable quality.
2. `actuator_only_no_benefit`: real actuator works but no system benefit was measured.
3. `partial_free_blocked`: suffix-only physical release is not safe in vLLM V1; fallback route required.

## Evidence Table

| Metric | vLLM-default | full-recompute | greedy | ContractKV-anchored |
| --- | ---: | ---: | ---: | ---: |
| completed_requests | | | | |
| SLO-compliant req/s | | | | |
| total_blocks_freed | | | | |
| mean quality drop | | | | |

## Boundaries

This phase does not implement arbitrary interior segment stitching or MiniPIC-style position-independent reuse.

## Decision For Phase 11

Choose one:

- Proceed to interior segment selective recompute.
- Proceed to prefix-cache canonical layout fallback.
- Tune anchor policy and rerun pressure experiments.
```

- [ ] **Step 2: Run full verification**

Run:

```powershell
python -m unittest discover -s tests -v
python -m py_compile scripts/build_anchor_residency_plan.py scripts/audit_vllm_v1_suffix_free.py scripts/install_vllm_v1_anchor_recompute_probe.py scripts/build_anchor_recompute_probe_summary.py scripts/run_recompute_policy_pressure_eval.py scripts/evaluate_recompute_policy_quality.py
git diff --check
```

Expected:

```text
OK
no diff-check output
```

- [ ] **Step 3: Server cleanup verification**

Run:

```powershell
& 'E:\PuTTy\plink.exe' -ssh -batch -pw '12345678' -hostkey 'SHA256:hRNlxitqGzUJog3+HuGNgzd37IF62CQQXq/swz4us7M' user@10.15.0.47 'ps -eo pid,args | grep vllm.entrypoints.openai.api_server | grep -v grep || true; nvidia-smi --query-gpu=index,name,memory.used,memory.total --format=csv,noheader; LC_ALL=C df -hP / /media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9'
```

Expected:

```text
no vLLM process
GPU memory near idle
8T disk remains primary experiment location
```

- [ ] **Step 4: Commit and push**

Run:

```powershell
git add docs/phase10_5_real_recompute_policy_closeout.md
git commit -m "Close out Phase 10.5 recompute policy evaluation"
git push origin main
```

---

### Task 9: Prefix-Cache Fallback If Suffix-Free Is Blocked

**Use only if Task 3 reports `suffix_free_gate=blocked` or Task 5 cannot make a request complete after suffix-only release.**

**Files:**

- Create: `scripts/run_prefix_cache_layout_eval.py`
- Output: `results/hard_systems/prefix_cache_layout_real_metric_v0.csv`
- Report: `docs/phase10_5_prefix_cache_fallback_report.md`

- [ ] **Step 1: Compare three layouts**

Policies:

```text
raw-order prompt + prefix cache
ContractKV canonical-layout prompt + prefix cache
no prefix cache
```

Metrics:

```text
TTFT mean/p95
SLO-compliant req/s
prefix cache hit/reuse if observable
real output score
quality drop
```

- [ ] **Step 2: Success criterion**

Accept fallback as useful only if:

```text
TTFT improves by >= 10%
or SLO-compliant req/s improves by >= 10%
and real output quality does not drop beyond 3%
```

- [ ] **Step 3: Report boundary**

The report must state:

```text
Prefix-cache fallback is a real vLLM metric route, but it is weaker than hard block/residency control.
```

---

## Self-Review

Spec coverage:

- Phase 10.5A anchor planner: Task 1-2.
- Phase 10.5B anchored recompute actuator: Task 3-5.
- Policy comparison: Task 6.
- Quality verification: Task 7.
- Closeout and Phase 11 decision: Task 8.
- Fallback if suffix-free is blocked: Task 9.

Boundary checks:

- No arbitrary middle-segment hole punching in Phase 10.5.
- No MiniPIC/FusionRAG dependency in Phase 10.5 implementation.
- No system-benefit claim before pressure and quality metrics exist.
- Phase 10.4B full recompute remains baseline, not the final method.

Execution order:

```text
10.5A planner
-> suffix-free audit
-> anchored recompute POC
-> pressure policy eval
-> quality eval
-> closeout
```
