"""Capacity geometry of already archived strict traces; not a GPU prediction."""
import argparse
import json
from pathlib import Path


def lines(p): return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def main(root, output):
    study = root/"results/tsc_behavior_scope_repair_20261020"
    jobs = json.loads((study/"validation_jobs_v4.json").read_text())["jobs"]
    result = []
    for job in jobs:
        if job["policy"] != "Strict-exact": continue
        cell = study/"runs"/job["id"]/"attempt1"
        rows = lines(cell/"responses.jsonl")
        native = [r for r in lines(cell/"metrics.jsonl") if r.get("event") == "prefix_cache_request_observation" and r.get("initial_prefill_observation")]
        regs = [r for r in rows if r["row_type"] == "registration" and r["certificate"]["certificate_issued"]]
        groups = {r["source_group"]: r["certificate"]["committed_tokens"]//16 for r in regs}
        lower = []
        for row in rows:
            if row["row_type"] != "business" or row["compiled"]: continue
            ids = row["result"]["prompt_token_ids"]
            own = [r for r in regs if r["source_group"] == row["source_group"]]
            common = 0
            if own:
                for a, b in zip(ids, own[0]["plan"]["prompt_token_ids"]):
                    if a != b: break
                    common += 1
            active = (len(ids)+len(row["result"]["output_token_ids"])-1)//16
            lower.append(dict(source=row["source_group"], tenant=row["tenant"], observed_active_full_blocks=active,
                              all_certified_plus_active_Raw_full_blocks=sum(groups.values())+active-common//16))
        result.append(dict(model=job["model"], repeat=job["repeat"], actual_pool_blocks=sorted({r["total_gpu_blocks"] for r in native}),
            authorized_stable_groups_blocks=groups, all_authorized_stable_blocks=sum(groups.values()),
            largest_observed_active_Raw_requirement=max(x["observed_active_full_blocks"] for x in lower),
            max_all_certified_plus_active_Raw_lower_bound=max(x["all_certified_plus_active_Raw_full_blocks"] for x in lower),
            observations=lower, note="Posthoc capacity geometry using actual prompt/output lengths. Not a simulated speedup or proof a priority policy will help."))
    value = dict(source_archive="96fc6281f0049ba3f374c2be1177d5edd76d6c2144acc2dc1ca10f895e8ac3b2", rows=result, new_GPU_requests=0)
    with output.open("x", encoding="utf-8") as f: json.dump(value, f, indent=2); f.write("\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args(); main(a.root, a.output)
