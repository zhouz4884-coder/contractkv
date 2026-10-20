"""Verify every archived byte, then recompute scores/costs and eviction traces."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text(encoding="utf-8"))


def main(root, restore, receipt_output=None):
    rel = Path("results/tsc_exploratory_mechanisms_20261020")
    study = root/rel
    evidence = study/"evidence_v1"
    receipt = read(evidence/"receipt_v1.json")
    archive = evidence/receipt["archive"]
    assert sha(archive) == receipt["sha256"] and archive.stat().st_size == receipt["bytes"]
    assert not restore.exists(), "Do not overwrite a prior independent restore"
    destination = receipt_output or study/"local_independent_recompute_v1.json"
    if receipt_output is None and destination.exists():
        destination = restore/"verification_receipt_v1.json"
    assert not destination.exists()
    restore.mkdir(parents=True)
    inventory = read(evidence/"inventory_v1.json")["files"]
    expected = {r["path"]: r["sha256"] for r in inventory}
    seen = set()
    with tarfile.open(archive, "r:gz") as t:
        for m in t.getmembers():
            assert m.isfile() and not Path(m.name).is_absolute() and ".." not in Path(m.name).parts
            p = restore/m.name
            assert p.resolve().is_relative_to(restore.resolve())
            data = t.extractfile(m).read()
            assert m.name in expected and hashlib.sha256(data).hexdigest() == expected[m.name]
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("xb") as f: f.write(data)
            seen.add(m.name)
    assert seen == set(expected) and len(seen) == receipt["regular_files"]
    analysis = restore/"independent_analysis_v3.json"
    forensic = restore/"independent_forensics_v1.json"
    for script, target in [("tsc_exploratory_analysis_v3.py", analysis), ("tsc_exploratory_residency_forensics_v1.py", forensic)]:
        done = subprocess.run([sys.executable, "-B", str(restore/"scripts"/script), "--root", str(restore), "--output", str(target)],
                              cwd=restore, capture_output=True, text=True)
        (restore/(script+".recompute.log")).write_text(done.stdout+done.stderr, encoding="utf-8")
        assert done.returncode == 0, done.stderr
    assert read(analysis) == read(study/"analysis_v3.json")
    assert read(forensic) == read(study/"residency_forensics_v1.json")
    for name, value in expected.items(): assert sha(restore/name) == value
    result = dict(status="PASS", archive_sha256=receipt["sha256"], members=len(seen),
        all_archived_inputs_unchanged=True, full_scientific_analysis_all_values_exact=True,
        actual_hash_eviction_forensics_all_values_exact=True, new_GPU_requests=0,
        restore_root=str(restore), analysis_source_sha256=sha(restore/"scripts/tsc_exploratory_analysis_v3.py"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as f: json.dump(result, f, indent=2); f.write("\n")
    print(json.dumps(result))


if __name__ == "__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--restore",type=Path,required=True)
    p.add_argument("--receipt-output",type=Path)
    a=p.parse_args();main(a.root.resolve(),a.restore.resolve(),a.receipt_output)
