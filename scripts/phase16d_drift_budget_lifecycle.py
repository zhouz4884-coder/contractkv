#!/usr/bin/env python3
"""Phase 16D drift-bounded certificate lifecycle calibration."""

from __future__ import annotations

import argparse
import csv
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


RAW_FIELDS = [
    "partition",
    "policy",
    "session_id",
    "family",
    "turn",
    "semantic_state",
    "residency_state",
    "hard_invalidated",
    "drift_score",
    "token_drift",
    "position_drift",
    "source_drift",
    "margin_drift",
    "future_mismatch",
    "retained_prefix_gain",
    "renewal_cost_ms",
    "decision",
]

SUMMARY_FIELDS = [
    "partition",
    "policy",
    "sessions",
    "future_turns",
    "certificate_coverage",
    "renewal_rate",
    "future_mismatch_rate",
    "future_mismatch_wilson95_upper",
    "mean_retained_prefix_gain",
    "mean_renewal_cost_ms",
    "objective",
    "gate_pass",
    "claim_boundary",
]


def wilson_upper(failures: int, total: int, z: float = 1.959963984540054) -> float:
    if total <= 0:
        return 1.0
    phat = failures / total
    denom = 1 + z * z / total
    center = phat + z * z / (2 * total)
    margin = z * ((phat * (1 - phat) + z * z / (4 * total)) / total) ** 0.5
    return (center + margin) / denom


@dataclass
class Certificate:
    stable_hash: str
    dag_hash: str
    layout_hash: str
    tool_schema_hash: str
    output_contract: str
    stable_tokens: int
    issued_query_distance: int
    issued_margin_q10: float
    issued_sources: frozenset[str]
    cumulative_dynamic_tokens: int = 0
    semantic_state: str = "VALID"
    residency_state: str = "HOT"


@dataclass(frozen=True)
class TurnEvidence:
    dynamic_tokens: int
    query_distance: int
    margin_q10: float
    source_ids: frozenset[str]
    tool_schema_hash: str
    stable_hash: str
    dag_hash: str
    layout_hash: str
    output_contract: str
    answer_changed: bool
    retained_prefix_gain: float


@dataclass(frozen=True)
class Policy:
    name: str
    ttl: int | None = None
    use_token: bool = False
    use_position: bool = False
    use_source: bool = False
    use_margin: bool = False
    w_token: float = 0.20
    w_position: float = 0.70
    w_source: float = 1.50
    w_margin: float = 2.00
    tau_token: float = 0.60
    tau_position: float = 0.15
    tau_margin: float = 0.20


def jaccard_distance(left: frozenset[str], right: frozenset[str]) -> float:
    if not left and not right:
        return 0.0
    return 1.0 - (len(left & right) / max(len(left | right), 1))


def normalize(value: float, tau: float) -> float:
    return min(1.0, value / max(tau, 1e-9))


def hard_invalidated(cert: Certificate, turn: TurnEvidence) -> bool:
    return any(
        [
            cert.stable_hash != turn.stable_hash,
            cert.dag_hash != turn.dag_hash,
            cert.layout_hash != turn.layout_hash,
            cert.tool_schema_hash != turn.tool_schema_hash,
            cert.output_contract != turn.output_contract,
        ]
    )


def update_certificate(cert: Certificate, turn: TurnEvidence, policy: Policy, age: int) -> tuple[float, dict[str, float], bool]:
    if hard_invalidated(cert, turn):
        cert.semantic_state = "REVOKED"
        return 1.0, {"token": 0.0, "position": 0.0, "source": 0.0, "margin": 0.0}, True
    if policy.ttl is not None and age > policy.ttl:
        cert.semantic_state = "RENEWAL_PENDING"
        return 1.0, {"token": 0.0, "position": 0.0, "source": 0.0, "margin": 0.0}, False

    cert.cumulative_dynamic_tokens += turn.dynamic_tokens
    d_token = cert.cumulative_dynamic_tokens / max(cert.stable_tokens, 1)
    d_pos = abs(turn.query_distance - cert.issued_query_distance) / max(cert.stable_tokens, 1)
    d_src = jaccard_distance(cert.issued_sources, turn.source_ids)
    d_margin = max(0.0, (cert.issued_margin_q10 - turn.margin_q10) / (abs(cert.issued_margin_q10) + 1e-6))

    score = 0.0
    if policy.use_token:
        score += policy.w_token * normalize(d_token, policy.tau_token)
    if policy.use_position:
        score += policy.w_position * normalize(d_pos, policy.tau_position)
    if policy.use_source:
        score += policy.w_source * d_src
    if policy.use_margin:
        score += policy.w_margin * normalize(d_margin, policy.tau_margin)
    if score >= 1.0:
        cert.semantic_state = "RENEWAL_PENDING"
    return score, {"token": d_token, "position": d_pos, "source": d_src, "margin": d_margin}, False


def build_session(session_id: int, family: str, rng: random.Random, turns: int) -> tuple[Certificate, list[TurnEvidence]]:
    stable_tokens = {"qasper": 3200, "repobench": 2600, "ruler": 4096, "tool_agent": 1800}[family]
    base_sources = frozenset({f"{family}_src_{session_id % 7}", f"{family}_src_common"})
    cert = Certificate(
        stable_hash=f"{family}:stable:{session_id}",
        dag_hash=f"{family}:dag",
        layout_hash=f"{family}:layout:caposc",
        tool_schema_hash=f"{family}:tool:v1",
        output_contract=f"{family}:contract",
        stable_tokens=stable_tokens,
        issued_query_distance=rng.randint(64, 192),
        issued_margin_q10=rng.uniform(0.8, 2.5),
        issued_sources=base_sources,
    )
    evidence = []
    for turn in range(1, turns):
        source_changed = rng.random() < {"qasper": 0.20, "repobench": 0.16, "ruler": 0.12, "tool_agent": 0.28}[family]
        tool_changed = family == "tool_agent" and rng.random() < 0.12
        target_changed = rng.random() < {"qasper": 0.18, "repobench": 0.22, "ruler": 0.10, "tool_agent": 0.20}[family]
        sources = base_sources
        if source_changed or target_changed:
            sources = frozenset({f"{family}_src_new_{session_id}_{turn}", f"{family}_src_common"})
        margin = cert.issued_margin_q10 - (
            rng.uniform(0.45, 1.00) if target_changed else rng.uniform(0.0, 0.18)
        )
        dynamic_tokens = rng.randint(80, 420 if family != "tool_agent" else 700)
        query_distance = cert.issued_query_distance + (
            rng.randint(int(0.25 * stable_tokens), int(0.45 * stable_tokens))
            if target_changed
            else rng.randint(-80, 80)
        )
        evidence.append(
            TurnEvidence(
                dynamic_tokens=dynamic_tokens,
                query_distance=query_distance,
                margin_q10=margin,
                source_ids=sources,
                tool_schema_hash=f"{family}:tool:v2" if tool_changed else cert.tool_schema_hash,
                stable_hash=cert.stable_hash,
                dag_hash=cert.dag_hash,
                layout_hash=cert.layout_hash,
                output_contract=cert.output_contract,
                answer_changed=source_changed or tool_changed or target_changed,
                retained_prefix_gain=rng.uniform(0.45, 0.82),
            )
        )
    return cert, evidence


def clone_cert(cert: Certificate) -> Certificate:
    return Certificate(
        stable_hash=cert.stable_hash,
        dag_hash=cert.dag_hash,
        layout_hash=cert.layout_hash,
        tool_schema_hash=cert.tool_schema_hash,
        output_contract=cert.output_contract,
        stable_tokens=cert.stable_tokens,
        issued_query_distance=cert.issued_query_distance,
        issued_margin_q10=cert.issued_margin_q10,
        issued_sources=cert.issued_sources,
    )


def renew_from_turn(cert: Certificate, turn: TurnEvidence) -> Certificate:
    return Certificate(
        stable_hash=turn.stable_hash,
        dag_hash=turn.dag_hash,
        layout_hash=turn.layout_hash,
        tool_schema_hash=turn.tool_schema_hash,
        output_contract=turn.output_contract,
        stable_tokens=cert.stable_tokens,
        issued_query_distance=turn.query_distance,
        issued_margin_q10=turn.margin_q10,
        issued_sources=turn.source_ids,
    )


def run_policy(policy: Policy, sessions: list[tuple[int, str, Certificate, list[TurnEvidence]]], partition: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for session_id, family, base_cert, turns in sessions:
        cert = clone_cert(base_cert)
        cert_age = 0
        for turn_index, turn in enumerate(turns, start=1):
            cert_age += 1
            score, parts, hard = update_certificate(cert, turn, policy, cert_age)
            valid = cert.semantic_state == "VALID"
            mismatch = valid and turn.answer_changed
            decision = "use_caposc" if valid else "renew_or_raw"
            rows.append(
                {
                    "policy": policy.name,
                    "partition": partition,
                    "session_id": session_id,
                    "family": family,
                    "turn": turn_index,
                    "semantic_state": cert.semantic_state,
                    "residency_state": cert.residency_state,
                    "hard_invalidated": hard,
                    "drift_score": round(score, 6),
                    "token_drift": round(parts["token"], 6),
                    "position_drift": round(parts["position"], 6),
                    "source_drift": round(parts["source"], 6),
                    "margin_drift": round(parts["margin"], 6),
                    "future_mismatch": mismatch,
                    "retained_prefix_gain": round(turn.retained_prefix_gain if valid else 0.0, 6),
                    "renewal_cost_ms": 450.0 if not valid else 0.0,
                    "decision": decision,
                }
            )
            if not valid:
                cert = renew_from_turn(cert, turn)
                cert_age = 0
    return rows


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    keys = sorted({(str(row["partition"]), str(row["policy"])) for row in rows})
    for partition, policy in keys:
        rs = [row for row in rows if row["policy"] == policy and row["partition"] == partition]
        sessions = len({row["session_id"] for row in rs})
        future = len(rs)
        mismatches = sum(1 for row in rs if row["future_mismatch"] in {True, "True", "true"})
        covered = [row for row in rs if row["decision"] == "use_caposc"]
        renewals = [row for row in rs if row["decision"] != "use_caposc"]
        gains = [float(row["retained_prefix_gain"]) for row in rs]
        renewal_cost = [float(row["renewal_cost_ms"]) for row in rs]
        objective = (sum(gains) / max(future, 1)) - 0.0005 * (sum(renewal_cost) / max(future, 1))
        upper = wilson_upper(mismatches, future)
        out.append(
            {
                "policy": policy,
                "partition": partition,
                "sessions": sessions,
                "future_turns": future,
                "certificate_coverage": round(len(covered) / max(future, 1), 6),
                "renewal_rate": round(len(renewals) / max(future, 1), 6),
                "future_mismatch_rate": round(mismatches / max(future, 1), 6),
                "future_mismatch_wilson95_upper": round(upper, 6),
                "mean_retained_prefix_gain": round(sum(gains) / max(future, 1), 6),
                "mean_renewal_cost_ms": round(sum(renewal_cost) / max(future, 1), 6),
                "objective": round(objective, 6),
                "gate_pass": upper <= 0.03 and len(covered) / max(future, 1) >= 0.50,
                "claim_boundary": "Synthetic answer-changing drift calibration pool; thresholds require real future-turn validation before deployment.",
            }
        )
    return out


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{field: row.get(field, "") for field in fields} for row in rows])


def run(args: argparse.Namespace) -> None:
    rng = random.Random(args.seed)
    families = ["qasper", "repobench", "ruler", "tool_agent"]
    sessions = []
    sid = 0
    for family in families:
        for _ in range(args.sessions_per_family):
            cert, turns = build_session(sid, family, rng, args.turns)
            sessions.append((sid, family, cert, turns))
            sid += 1
    calibration = [item for item in sessions if item[0] % 2 == 0]
    held_out = [item for item in sessions if item[0] % 2 == 1]
    base_policies = [
        Policy("fixed_ttl_1", ttl=1),
        Policy("fixed_ttl_3", ttl=3),
        Policy("fixed_ttl_5", ttl=5),
        Policy("token_only", use_token=True),
        Policy("token_position", use_token=True, use_position=True),
        Policy("full_native_drift", use_token=True, use_position=True, use_source=True, use_margin=True),
    ]
    calibrated = select_calibrated_policy(calibration)
    policies = [*base_policies, calibrated]
    raw_rows: list[dict[str, Any]] = []
    for policy in policies:
        raw_rows.extend(run_policy(policy, calibration, "calibration"))
        raw_rows.extend(run_policy(policy, held_out, "held_out"))
    write_csv(args.raw_output, raw_rows, RAW_FIELDS)
    write_csv(args.summary_output, summarize(raw_rows), SUMMARY_FIELDS)


def metric_tuple(rows: list[dict[str, Any]]) -> tuple[float, float, float, float, float]:
    total = len(rows)
    covered = [row for row in rows if row["decision"] == "use_caposc"]
    mismatches = sum(1 for row in rows if row["future_mismatch"] in {True, "True", "true"})
    gains = sum(float(row["retained_prefix_gain"]) for row in rows) / max(total, 1)
    costs = sum(float(row["renewal_cost_ms"]) for row in rows) / max(total, 1)
    objective = gains - 0.0005 * costs
    return len(covered) / max(total, 1), mismatches / max(total, 1), wilson_upper(mismatches, total), gains, objective


def select_calibrated_policy(sessions: list[tuple[int, str, Certificate, list[TurnEvidence]]]) -> Policy:
    candidates = []
    for w_source in [1.2, 1.3, 1.4, 1.5, 1.6, 1.8]:
        for w_position in [0.2, 0.35, 0.5, 0.7]:
            for w_margin in [0.2, 0.5, 0.8, 1.2, 1.6, 2.0]:
                for tau_position in [0.15, 0.2, 0.3, 0.45]:
                    for tau_margin in [0.2, 0.35, 0.5, 0.8]:
                        policy = Policy(
                            name="calibrated_full_native_drift",
                            use_token=True,
                            use_position=True,
                            use_source=True,
                            use_margin=True,
                            w_token=0.20,
                            w_position=w_position,
                            w_source=w_source,
                            w_margin=w_margin,
                            tau_position=tau_position,
                            tau_margin=tau_margin,
                        )
                        rows = run_policy(policy, sessions, "calibration")
                        coverage, mismatch, upper, gain, objective = metric_tuple(rows)
                        candidates.append((upper <= 0.03 and coverage >= 0.50, objective, coverage, -upper, gain, policy))
    passing = [item for item in candidates if item[0]]
    if passing:
        return sorted(passing, key=lambda item: (item[1], item[2], item[3], item[4]), reverse=True)[0][-1]
    return sorted(candidates, key=lambda item: (item[3], item[1], item[2]), reverse=True)[0][-1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=16401)
    parser.add_argument("--sessions-per-family", type=int, default=40)
    parser.add_argument("--turns", type=int, default=6)
    parser.add_argument("--raw-output", type=Path, default=Path("results/runtime/phase16d_drift_budget_raw_v0.csv"))
    parser.add_argument("--summary-output", type=Path, default=Path("results/runtime/phase16d_drift_budget_summary_v0.csv"))
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
