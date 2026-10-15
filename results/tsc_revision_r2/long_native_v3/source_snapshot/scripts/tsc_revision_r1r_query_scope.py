"""Query-bound metadata-only scope identities for the repair study."""
import re
from scripts.phase17_live_common import digest

DYNAMIC = {"TOOL_OBS", "USER_QUERY", "CHAT_HISTORY", "SCRATCHPAD"}
RENDERER_VERSION = "r1r-query-bound-metadata-only-v1"


def query_scope(case, system_message, budget, model_identity, policy_hash):
    queries = [s for s in case["segments"] if s["segment_type"] == "USER_QUERY"]
    if len(queries) != 1:
        raise ValueError("one explicit query segment is required")
    if any(s["segment_type"] in {"CHAT_HISTORY", "SCRATCHPAD"} for s in case["segments"]):
        raise ValueError("unqualified stateful suffix")
    for s in case["segments"]:
        if s["segment_type"] == "TOOL_OBS" and not re.fullmatch(
            r"\[PRIVATE_TOOL_OBS\] revision_session=[A-Za-z0-9_-]+; turn=\d+; status=(ready|completed|idle); no additional answer evidence\.",
            s["text"]):
            raise ValueError("metadata-only suffix schema mismatch")
    return digest({"query": queries[0]["text"], "system": system_message,
                   "stable": [(s["segment_id"],s["segment_type"],s["text"]) for s in case["segments"] if s["segment_type"] not in DYNAMIC],
                   "model":model_identity, "budget":budget, "seed":14014, "temperature":0,
                   "policy_hash":policy_hash, "renderer_version":RENDERER_VERSION})


def level_descent(maximum):
    if maximum == "L0": return []
    return [level for level in ("L3","L2","L1") if int(level[1:]) <= int(maximum[1:])]
