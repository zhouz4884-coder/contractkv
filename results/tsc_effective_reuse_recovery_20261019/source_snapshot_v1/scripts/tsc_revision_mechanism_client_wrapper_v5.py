"""Run the frozen diagnostic collector with one explicit admission bug repair."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import runpy
import sys


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(add_help=False)
    p.add_argument('--snapshot-root',type=Path,required=True)
    p.add_argument('--archived-client',type=Path,required=True)
    p.add_argument('--repair-module',type=Path,required=True)
    p.add_argument('--repair-manifest',type=Path,required=True)
    args,remaining=p.parse_known_args();snapshot=args.snapshot_root.resolve()
    manifest=json.loads(args.repair_manifest.read_text(encoding='utf-8'))
    assert sha(Path(__file__))==manifest['client_wrapper_sha256']
    assert sha(args.repair_module)==manifest['repair_module_sha256']
    assert args.archived_client.resolve().is_relative_to(snapshot)
    assert sha(args.archived_client)==manifest['unchanged_collector_sha256']
    sys.path.insert(0,str(snapshot))
    from scripts.tsc_revision_r2_admission import SingleShotRegistrar
    from scripts.contractkv_verifier import VerificationIncomplete
    module=Path(sys.modules[SingleShotRegistrar.__module__].__file__).resolve()
    assert module.is_relative_to(snapshot) and sha(module)==manifest['unchanged_original_admission_sha256']
    spec=importlib.util.spec_from_file_location('contractkv_fail_closed_v5',args.repair_module)
    fix=importlib.util.module_from_spec(spec);spec.loader.exec_module(fix)
    original=SingleShotRegistrar.register
    SingleShotRegistrar.register=fix.repaired_register(original,VerificationIncomplete)
    sys.argv=[str(args.archived_client),*remaining]
    try:runpy.run_path(str(args.archived_client),run_name='__main__')
    finally:SingleShotRegistrar.register=original


if __name__=='__main__':main()
