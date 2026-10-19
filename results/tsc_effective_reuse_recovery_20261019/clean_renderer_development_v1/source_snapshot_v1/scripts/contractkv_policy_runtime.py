#!/usr/bin/env python3
"""Runtime policy wrapper for ContractKV Python-level prototype."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.contractkv_segment_parser import parse_chat_segments
from scripts.cslo_solver_v0 import make_cost_lookup, make_risk_lookup, read_csv
from scripts.policies.common import contractkv_indep, contractkv_joint


POLICY_FNS: dict[str, Callable[..., dict[str, Any]]] = {
    "ContractKV-Joint": contractkv_joint,
    "ContractKV-Indep": contractkv_indep,
}


class ContractKVRuntime:
    def __init__(
        self,
        risk_summary_path: Path | str = Path("results/risk_ledger/quality_risk_summary_v0.csv"),
        cost_table_path: Path | str = Path("results/cost/segment_action_cost_table_v0.csv"),
        policy: str = "ContractKV-Joint",
        quality_budget: float = 0.02,
        slo_budget_ms: float = 200.0,
    ):
        self.risk_summary_path = Path(risk_summary_path)
        self.cost_table_path = Path(cost_table_path)
        self.policy = policy
        self.quality_budget = quality_budget
        self.slo_budget_ms = slo_budget_ms
        started = time.perf_counter()
        self.risk_lookup = make_risk_lookup(read_csv(self.risk_summary_path))
        self.risk_lookup_ms = (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        self.cost_lookup = make_cost_lookup(read_csv(self.cost_table_path))
        self.cost_lookup_ms = (time.perf_counter() - started) * 1000

    def decide_sample(self, sample: dict[str, Any]) -> tuple[dict[str, Any], dict[str, float]]:
        started = time.perf_counter()
        policy_fn = POLICY_FNS[self.policy]
        decision = policy_fn(sample, self.risk_lookup, self.cost_lookup, self.quality_budget, self.slo_budget_ms)
        policy_ms = (time.perf_counter() - started) * 1000
        timings = {
            "parse_ms": float(sample.get("metadata", {}).get("parse_ms", 0.0)),
            "risk_lookup_ms": self.risk_lookup_ms,
            "cost_lookup_ms": self.cost_lookup_ms,
            "policy_ms": policy_ms,
        }
        return decision, timings

    def decide(self, request: dict[str, Any]) -> tuple[dict[str, Any], dict[str, float]]:
        started = time.perf_counter()
        sample = parse_chat_segments(request)
        parse_ms = (time.perf_counter() - started) * 1000
        decision, timings = self.decide_sample(sample)
        timings["parse_ms"] = parse_ms
        return decision, timings
