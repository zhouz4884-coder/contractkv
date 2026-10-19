"""Run the unchanged frozen R4 live loop with the declared fidelity adapter."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import tsc_revision_r4_live as frozen_client
from scripts.tsc_revision_r4_fidelity_adapter import ADAPTER_VERSION, installed_adapter


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--input-adapter-record', type=Path, required=True)
    own, remaining = parser.parse_known_args()
    if own.input_adapter_record.exists():
        raise RuntimeError('Preserve every adapter execution record')
    own.input_adapter_record.parent.mkdir(parents=True, exist_ok=True)
    record = {
        'schema_version': 'tsc-r4.task-fidelity-live-adapter.v1',
        'adapter': ADAPTER_VERSION,
        'source_files': {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in
                         [Path(__file__), Path('scripts/tsc_revision_r4_fidelity_adapter.py'),
                          Path('scripts/tsc_revision_r4_live.py')]},
        'text_change': 'Only the precommitted input trace packing; online builder uses word cap 0.',
        'metadata_change': 'CODE_PREFIX volatility 0 and cache_stability 1.',
        'output_contract': 'Unchanged one_python_statement; no bypass or output rewrite.',
        'unchanged_loop': True,
        'result': 'not_completed',
    }
    sys.argv = [sys.argv[0], *remaining]
    try:
        with installed_adapter():
            code = frozen_client.main()
        record['result'] = 'completed' if code == 0 else 'client_failure'
        record['client_exit_code'] = code
        return code
    except BaseException as error:
        record['error_type'] = type(error).__name__
        raise
    finally:
        own.input_adapter_record.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    raise SystemExit(main())
