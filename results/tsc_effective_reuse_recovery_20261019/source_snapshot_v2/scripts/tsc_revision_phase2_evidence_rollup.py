"""Join existing per-member/local recomputation proofs and rehash every part."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Preserve the previous local observation')
    names = ('diagnosis_v1', 'warm_reuse_v1', 'batch_reuse_v1', 'margin_smoke_v1',
             'profile_v1', 'development_pilot_v1', 'long_format_v2', 'long_native_v3',
             'long_extent_v4', 'validation_v1')
    studies, failures = [], []
    for phase, selected in (('tsc_revision_r2', names), ('tsc_revision_r3', ('validation_v1',))):
        for name in selected:
            base = args.root / 'results' / phase / name
            proof_paths = {key: base / filename for key, filename in (
                ('archive_manifest', 'raw_evidence_archive_manifest_v1.json'),
                ('parts_manifest', 'raw_evidence_parts_manifest_v1.json'),
                ('member_verification', 'local_archive_verification_v1.json'),
                ('independent_recomputation', 'local_recheck_v1.json'))}
            proofs = {key: json.loads(path.read_text(encoding='utf-8')) for key, path in proof_paths.items()}
            archive, parts = proofs['archive_manifest'], proofs['parts_manifest']
            verification, recomputation = proofs['member_verification'], proofs['independent_recomputation']
            part_checks = []
            for part in parts['parts']:
                path = base / part['file']
                match = path.is_file() and path.stat().st_size == part['bytes'] and sha(path) == part['sha256']
                part_checks.append({'file': part['file'], 'bytes': part['bytes'], 'matches': match})
            complete = (verification['all_hashes_match'] and recomputation['all_pass'] and
                        archive['archive_sha256'] == parts['archive_sha256'] == verification['archive_sha256'] and
                        archive['member_files'] == verification['members_verified'] and
                        len(part_checks) > 0 and all(r['matches'] for r in part_checks))
            if not complete:
                failures.append(phase + '/' + name)
            studies.append({'study': phase + '/' + name, 'archive_sha256': archive['archive_sha256'],
                            'members_verified': verification['members_verified'],
                            'proof_file_sha256': {key: sha(path) for key, path in proof_paths.items()},
                            'part_checks': part_checks, 'complete': bool(complete)})
    result = {'schema_version': 'tsc.phase2.local-evidence-rollup.v1',
              'timestamp': datetime.now(timezone.utc).isoformat(),
              'analysis_source_sha256': sha(Path(__file__)), 'studies': studies,
              'completed_studies': len(studies),
              'verified_archive_members_including_repeated_snapshots': sum(r['members_verified'] for r in studies),
              'rehashed_parts': sum(len(r['part_checks']) for r in studies),
              'all_local_proofs_and_parts_pass': not failures, 'failures': failures,
              'boundary': 'Transport/member identity and independently recomputed tables. Experimental scientific success is separate.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items() if key != 'studies'}))
    return 0 if not failures else 2


if __name__ == '__main__':
    raise SystemExit(main())
