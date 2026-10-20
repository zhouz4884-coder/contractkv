"""Link observed prefix-head reclamations to later real cache misses."""
import argparse
import ast
from collections import Counter
import json
from pathlib import Path


def lines(p): return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def hashhex(value):
    try:
        obj = ast.literal_eval(value)
        return bytes(obj).hex()
    except (ValueError, TypeError, SyntaxError):
        return None


def main(root, output):
    study = root/"results/tsc_exploratory_mechanisms_20261020"
    jobs = json.loads((study/"jobs_v1.json").read_text())["jobs"]
    results = []
    for job in jobs:
        cell = study/"runs"/job["id"]/"attempt1"
        rr = lines(cell/"responses.jsonl")
        ss = json.loads((cell/"summary_v1.json").read_text())
        native = {r["request_id"]:r for r in lines(cell/"metrics.jsonl") if r.get("event") == "prefix_cache_request_observation" and r.get("initial_prefill_observation")}
        trace = [r for r in lines(cell/"mechanism_trace.jsonl") if r["event"] == "allocate"
                 and ss["service_begin_time"] <= r["monotonic_s"] <= ss["service_end_time"]]
        regs = [r for r in rr if r["row_type"] == "registration" and r["certificate"]["certificate_issued"]]
        business = [r for r in rr if r["row_type"] == "business"]
        intervals = []
        for row in rr:
            if row["row_type"] in ["business", "reference_generation"]:
                r = row["result"]
                intervals.append((r["first_time"]-r["ttft_ms"]/1000, r["end_time"], row["row_type"], row["source_group"]))
            elif row["row_type"] == "verification_request":
                reply = next(x for x in rr if x["row_type"] == "verification_response" and x["request_id"] == row["request_id"])
                intervals.append((row["record_monotonic_s"],reply["record_monotonic_s"],"verification",row["payload"]["stable_content_hash"]))
        known = {}
        for row in business:
            if not row["compiled"]: continue
            reg = next(r for r in regs if (r["source_group"],r["tenant"],r["turn"]) == (row["source_group"],row["tenant"],row["turn"]))
            event = native[row["result"]["request_id"]]
            n = reg["certificate"]["committed_tokens"]//16
            if event["prefix_hit_tokens"] >= n*16:
                hh = event["physical_block_hashes"][:n]
                assert len(hh) == n and all(hh)
                if row["source_group"] in known: assert known[row["source_group"]] == hh
                known[row["source_group"]] = hh
        misses = []
        for row in business:
            if not row["compiled"]: continue
            event = native[row["result"]["request_id"]]
            if event["prefix_hit_tokens"]: continue
            source = row["source_group"]
            if source not in known:
                misses.append(dict(source=source, sequence=row["sequence"], observed_zero_hit=True, hash_chain_unavailable=True))
                continue
            end = row["result"]["first_time"]-row["result"]["ttft_ms"]/1000
            anchors = [r["record_monotonic_s"] for r in regs if r["source_group"] == source and r["record_monotonic_s"] < end]
            anchors += [r["result"]["end_time"] for r in business if r["source_group"] == source and r["compiled"] and r["result"]["end_time"] < end]
            begin = max(anchors)
            head, hashes = known[source][0], set(known[source])
            events, causes = [], Counter()
            for e in trace:
                if not begin <= e["monotonic_s"] < end: continue
                evicted = [hashhex(v) for v in e["evicted_hashes"]]
                hit = set(evicted)&hashes
                if not hit: continue
                cause = next(((kind,s) for a,b,kind,s in intervals if a <= e["monotonic_s"] <= b), ("unassigned",None))
                causes[cause[0]+":"+str(cause[1])] += len(hit)
                events.append(dict(monotonic_s=e["monotonic_s"], matching_prefix_hashes=len(hit),
                                   prefix_head_reclaimed=head in hit, cause=list(cause)))
            misses.append(dict(source=source, tenant=row["tenant"], sequence=row["sequence"], observed_zero_hit=True,
                previous_warm_anchor=begin, next_business_send=end,
                actual_prefix_head_reclaimed=any(e["prefix_head_reclaimed"] for e in events),
                reclamation_causes=dict(causes), actual_events=events))
        results.append(dict(model=job["model"], arm=job["arm"], compiled_zero_hits=len(misses),
                            zero_hits_with_observed_head_reclamation=sum(r.get("actual_prefix_head_reclaimed",False) for r in misses),
                            misses=misses))
    with output.open("x",encoding="utf-8") as f:
        json.dump(dict(status="COMPLETE",rows=results,note="Exact observed block hashes; hash copies can repeat. This is a causal sequence trace, not a randomized eviction-policy effect estimate."),f,indent=2);f.write("\n")


if __name__ == "__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    a=p.parse_args();main(a.root,a.output)
