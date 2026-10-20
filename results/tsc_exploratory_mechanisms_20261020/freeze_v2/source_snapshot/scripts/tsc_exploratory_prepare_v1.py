"""Freeze an appendix-only, outcome-unselected diagnostic matrix."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
REL = Path("results/tsc_exploratory_mechanisms_20261020")
PARENT = Path("results/tsc_behavior_scope_repair_20261020")
MODELS = ["Qwen3-8B", "Mistral-7B-Instruct-v0.3"]
ARMS = ["Raw", "Strict", "TF-only", "Fused", "Fused-residency", "Raw-residency"]


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p, x):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("x", encoding="utf-8") as f: json.dump(x, f, indent=2); f.write("\n")


def main():
    study = ROOT/REL
    assert not study.exists()
    study.mkdir(parents=True)
    protocol = dict(schema="contractkv.optional-mechanism-diagnostic.v1", purpose="Appendix candidate, not a reviewer-required experiment or fifth core contribution",
        reviewer_priority_gate="results/tsc_reviewer_priority_audit_20261020/reviewer_experiment_recheck_v1.json",
        models=MODELS, arms=ARMS, max_cells=12, fresh_process_repeats=1,
        sources="ALL four previously opened validation sources from the behavior-scope repair, now reused as development. No new independent claims, no selection based on new results.",
        exact_scopes="Three QA sources x two tenant/turn conditions x two models = 12 QA scope conditions, including known rejections. Existing Repo remains L0.",
        input_set="validation", accesses_per_exact_scope=4, total_business=384,
        clock="serial closed backlog; identical inputs/order per arm; all online qualification, failures, native hooks and client costs included; server loading outside clock",
        budgets=dict(QA=128, Repo=384, max_model_len=16384, max_num_seqs=2, pool_blocks={MODELS[0]:1940, MODELS[1]:3550}),
        floors=dict(Raw=.0625, Candidate_and_EOS=.125), generation=dict(temperature=0, top_p=1, seed=14014),
        fusion="Actual Candidate decode and EOS logprobs captured before free; unchanged native verifier checks those observed rows; same PSTP delayed visibility and block-aligned commit; no separate private Candidate generation or teacher-forced forward",
        TF_only="Separate exploratory comparator: one Raw-witness teacher-forced verification without private candidate free generation; does NOT claim strict free-running evidence; all subsequent output changes retained",
        residency="Revocable second-chance priority in free queue, group FIFO budget 75% of physical pool, 120s TTL; reclaim under allocation pressure; never increment ref_cnt or fake a live request",
        generic_Raw_control="Same pool/budget/TTL/reclaim code, priority assigned to ordinary completed prompt cache prefixes; generic replacement gain kept separate from certified-state gain",
        trace="Same allocation tracing hook in all arms; detailed full token/margin evidence for fused native requests only. Not a production throughput estimate.",
        statistical_limit="One process per arm/model and already-opened sources: descriptive paired mechanisms only, no CI or unseen-source performance inference.",
        stop="Complete at most 12 scheduled cells then stop. Infrastructure failures preserved and isolated; no threshold/source/SLO/reuse tuning to rescue results. Any fused ID/EOS/unauthorized publication violation -> disable branch and record NO-GO.",
        manuscript_and_response_edits=False,
        research_questions=["Does actual certified working set fit the measured pool, and what evicts it?", "Can one actual candidate decode preserve the original PASS/FAIL conditions and reduce total cost?", "Can reversible priority restore actual hits without hiding capacity or merely improving generic Raw?"])
    audit = json.loads((ROOT/protocol["reviewer_priority_gate"]).read_text())
    assert audit["status"] == "PASS" and audit["pending_required_GPU_cells_identified"] == 0
    write(study/"protocol_v1.json", protocol)
    jobs = []
    for wave, arm in enumerate(ARMS):
        for lane, model in enumerate(MODELS):
            name = f"dev-{model}-{arm}"
            job = dict(id=name, model=model, arm=arm, policy=arm, lane=lane, wave=wave,
                port=11600+wave*2+lane, input_set="validation", accesses=4, expected_business=32,
                pool_blocks=protocol["budgets"]["pool_blocks"][model],
                residency="CERTIFIED" if arm=="Fused-residency" else "GENERIC" if arm=="Raw-residency" else "OFF",
                job_file="jobs_v1/"+name+".json")
            jobs.append(job); write(study/job["job_file"], job)
    write(study/"jobs_v1.json", dict(jobs=jobs))
    frozen = study/"freeze_v1"
    shutil.copytree(ROOT/PARENT/"development_freeze_v4/source_snapshot", frozen/"source_snapshot")
    own = [p for p in (ROOT/"scripts").glob("tsc_exploratory_*v1.py")]
    own += [ROOT/"tests/test_tsc_exploratory_native_v1.py"]
    for p in own:
        target = frozen/"source_snapshot"/p.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(p, target)
    dependencies = [*own, study/"protocol_v1.json", study/"jobs_v1.json", *sorted((study/"jobs_v1").glob("*.json")),
        ROOT/PARENT/"inputs_validation_v1/sessions_v1.jsonl", ROOT/PARENT/"inputs_validation_v1/CPU_shapes_v1.jsonl",
        ROOT/"results/tsc_revision_mechanism_controls_20261018/preflight_v3/receipt_v1.json",
        ROOT/protocol["reviewer_priority_gate"]]
    files = [dict(path=p.relative_to(ROOT).as_posix(), sha256=sha(p)) for p in dependencies]
    snapshot = [dict(path=p.relative_to(frozen/"source_snapshot").as_posix(), sha256=sha(p))
                for p in sorted((frozen/"source_snapshot").rglob("*")) if p.is_file()]
    write(frozen/"freeze.json", dict(schema="contractkv.optional-mechanism-freeze.v1", files=files, snapshot_files=snapshot,
          parent_commit="5d2c7e9", new_GPU_inference=0, independent_validation=False))
    print(json.dumps(dict(freeze_sha256=sha(frozen/"freeze.json"), files=len(files), snapshot_files=len(snapshot), max_cells=12)))


if __name__ == "__main__": main()
