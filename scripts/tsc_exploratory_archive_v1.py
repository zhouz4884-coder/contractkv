"""Freeze completed raw evidence, excluding caches/weights/private helpers."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import sys
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.tsc_revision_final_raw_worker_v1 import resource_snapshot, foreign_pids
from scripts.tsc_tableIII_fullcost_worker_v3 import runtime_inventory


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text())
def write(p, x):
    with p.open("x", encoding="utf-8") as f: json.dump(x, f, indent=2); f.write("\n")


def main(root):
    study = root/"results/tsc_exploratory_mechanisms_20261020"
    assert read(study/"execution_state_v2.json")["status"] == "COMPLETE_PENDING_ANALYSIS"
    assert read(study/"analysis_v3.json")["status"] == "COMPLETE"
    assert read(study/"residency_forensics_v1.json")["status"] == "COMPLETE"
    snapshot = resource_snapshot()
    assert not foreign_pids(snapshot), "Do not archive/release over an active GPU task"
    frozen = read(study/"freeze_v2/freeze.json")
    for row in frozen["files"]: assert sha(root/row["path"]) == row["sha256"], row["path"]
    for row in frozen["snapshot_files"]:
        assert sha(study/"freeze_v2/source_snapshot"/row["path"]) == row["sha256"]
    parent = root/"results/tsc_revision_mechanism_controls_20261018/preflight_v3"
    parent_inventory = read(parent/"runtime_inventory_v1.json")["files"]
    assert runtime_inventory(parent/"runtime/vllm") == parent_inventory
    current_inventory = read(study/"preflight_v2/runtime_inventory_v1.json")["files"]
    assert runtime_inventory(study/"preflight_v2/runtime/vllm") == current_inventory
    registry = read(parent/"model_asset_registry_v1.json")
    stat_count = 0
    for model in registry["models"]:
        if model["model"] not in read(study/"protocol_v1.json")["models"]: continue
        for r in model["files"]:
            p = Path("/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models")/model["model"]/r["file"]
            st = p.stat(); assert (st.st_size, st.st_mtime_ns) == (r["bytes"], r["mtime_ns"])
            stat_count += 1
    write(study/"post_run_integrity_v1.json", dict(status="PASS", root_frozen_files=len(frozen["files"]),
        snapshot_frozen_files=len(frozen["snapshot_files"]), parent_shared_runtime_unchanged=True,
        experimental_runtime_matches_CPU_preflight=True, model_files_current_size_mtime_match=stat_count,
        final_resources=snapshot, new_model_weight_hash_claim=False,
        launch_file_epoch_s=(study/"launch_v2.json").stat().st_mtime,
        completion_state_epoch_s=(study/"execution_state_v2.json").stat().st_mtime,
        orchestration_wall_s_from_single_write_file_timestamps=(study/"execution_state_v2.json").stat().st_mtime-(study/"launch_v2.json").stat().st_mtime))
    members = {}
    def add(name, source):
        assert not Path(name).is_absolute() and ".." not in Path(name).parts
        if name in members: assert sha(members[name]) == sha(source), name
        else: members[name] = source
    for p in study.rglob("*"):
        if not p.is_file(): continue
        rel = p.relative_to(study)
        if any(x in {"cache", "tmp", "runtime", "evidence_v1", "__pycache__"} for x in rel.parts): continue
        if p.name.endswith((".lock", ".tmp")): continue
        add(p.relative_to(root).as_posix(), p)
    for r in frozen["files"]: add(r["path"], root/r["path"])
    # A standalone analysis root, using exactly the frozen import dependencies.
    for r in frozen["snapshot_files"]:
        add(r["path"], study/"freeze_v2/source_snapshot"/r["path"])
    for name in ["tsc_exploratory_analysis_v1.py", "tsc_exploratory_analysis_v2.py", "tsc_exploratory_analysis_v3.py",
                 "tsc_exploratory_residency_forensics_v1.py", "tsc_exploratory_archive_v1.py"]:
        add("scripts/"+name, root/"scripts"/name)
    evidence = study/"evidence_v1"
    evidence.mkdir(exist_ok=False)
    inventory = [dict(path=name, bytes=p.stat().st_size, sha256=sha(p)) for name, p in sorted(members.items())]
    write(evidence/"inventory_v1.json", dict(files=inventory))
    archive = evidence/"all_raw_evidence_v1.tar.gz"
    with tarfile.open(archive, "w:gz") as t:
        for name, p in sorted(members.items()): t.add(p, arcname=name, recursive=False)
    with tarfile.open(archive, "r:gz") as t:
        actual = {m.name: hashlib.sha256(t.extractfile(m).read()).hexdigest() for m in t.getmembers() if m.isfile()}
    assert actual == {r["path"]: r["sha256"] for r in inventory}
    for r in inventory: assert sha(members[r["path"]]) == r["sha256"]
    receipt = dict(status="PASS", archive=archive.name, bytes=archive.stat().st_size, sha256=sha(archive),
                   regular_files=len(inventory), all_member_hashes_verified=True, source_members_unchanged=True,
                   caches_runtime_copies_weights_credentials_excluded=True)
    write(evidence/"receipt_v1.json", receipt)
    print(json.dumps(receipt))


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--root", type=Path, required=True)
    main(p.parse_args().root)
