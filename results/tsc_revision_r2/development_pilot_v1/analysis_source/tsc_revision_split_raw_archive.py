"""Split an immutable gzip archive into GitHub-safe binary transport parts."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser(); p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--part-mib", type=int, default=32); a = p.parse_args()
    parts = []; index = 1; full_hash = hashlib.sha256()
    with a.archive.open("rb") as stream:
        while chunk := stream.read(a.part_mib * 1024 * 1024):
            full_hash.update(chunk)
            path = a.archive.with_name(a.archive.name + f".part{index:02d}")
            path.write_bytes(chunk)
            parts.append({"file":path.name,"bytes":len(chunk),"sha256":hashlib.sha256(chunk).hexdigest()})
            index += 1
    result = {"schema_version":"tsc-revision-archive-parts.v1","archive":a.archive.name,
              "archive_sha256":full_hash.hexdigest(),"parts":parts,
              "reassembly":"Concatenate parts in numeric order without modifying bytes, then verify the complete archive hash."}
    (a.archive.parent / "raw_evidence_parts_manifest_v1.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result))


if __name__ == "__main__": main()
