"""Pre-inference control addendum; preserve the unused v1 preflight/freeze."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "results/tsc_exploratory_mechanisms_20261020"


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p, value):
    with p.open("x", encoding="utf-8") as f: json.dump(value, f, indent=2); f.write("\n")


def main():
    assert not (STUDY/"freeze_v2").exists()
    addendum = dict(reason="Add explicit native release and real-engine abort/timeout/duplicate controls before ANY GPU inference",
        unchanged_main_matrix=True, main_cells=12, main_business=384,
        auxiliary_controls="After measured Fused service only, same live engine; at most 7 HTTP/cancel attempts + 8 read probes per model",
        auxiliary_clock="Separate time/cost ledger; no auxiliary request precedes or overlaps measured business",
        prior_v1_GPU_requests=0, default_runtime_unchanged=True,
        native_control_evidence="Actual pre-free cached-block hashes plus physical lookup after rejected/cancelled cold candidates",
        version="v2 execution entry points; v1 freeze and CPU preflight preserved unused")
    write(STUDY/"controls_addendum_v2.json", addendum)
    old = json.loads((STUDY/"freeze_v1/freeze.json").read_text())
    target = STUDY/"freeze_v2/source_snapshot"
    shutil.copytree(STUDY/"freeze_v1/source_snapshot", target)
    own = sorted((ROOT/"scripts").glob("tsc_exploratory_*v2.py"))
    for p in own:
        shutil.copyfile(p, target/"scripts"/p.name)
    old_files = {r["path"]: r for r in old["files"]}
    for p in own+[STUDY/"controls_addendum_v2.json"]:
        old_files[p.relative_to(ROOT).as_posix()] = dict(path=p.relative_to(ROOT).as_posix(), sha256=sha(p))
    files = [dict(path=p.relative_to(target).as_posix(), sha256=sha(p)) for p in sorted(target.rglob("*")) if p.is_file()]
    value = dict(schema="contractkv.optional-mechanism-freeze.v2", files=list(old_files.values()), snapshot_files=files,
        parent_freeze_v1_sha256=sha(STUDY/"freeze_v1/freeze.json"), new_GPU_inference=0,
        main_scientific_rules_unchanged=True, independent_validation=False)
    write(STUDY/"freeze_v2/freeze.json", value)
    print(json.dumps(dict(freeze_sha256=sha(STUDY/"freeze_v2/freeze.json"), snapshot_files=len(files))))


if __name__ == "__main__": main()
