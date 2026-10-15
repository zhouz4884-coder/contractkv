import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.audit_tsc_revision_r1_completion import live_cell


class CompletionAuditTests(unittest.TestCase):
    def make_cell(self, root, rows):
        directory = Path(root) / "cells" / "test"; directory.mkdir(parents=True)
        raw = directory / "raw.jsonl"
        raw.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        (directory / "summary.json").write_text(json.dumps({"source_sha256": hashlib.sha256(raw.read_bytes()).hexdigest()}))
        return directory

    def test_matching_file_hash_does_not_hide_duplicate_request_identity(self):
        with tempfile.TemporaryDirectory() as root:
            row = dict(row_type="future", session_id="s", turn_id=1, metric_join_success=True,
                       token_ids_available=True, success=True, scope_invalid_admission=False)
            self.make_cell(root, [row, row])
            audit = live_cell(Path(root), "test", 2)
            self.assertFalse(audit["execution_complete"])
            self.assertIn("request_count_or_identity_mismatch", audit["findings"])

    def test_rejected_certificate_with_published_tokens_fails_invariant(self):
        with tempfile.TemporaryDirectory() as root:
            future = dict(row_type="future", session_id="s", turn_id=1, metric_join_success=True,
                          token_ids_available=True, success=True, scope_invalid_admission=False)
            canary = dict(row_type="canary", certificate_issued=False, committed_tokens=16, registration_ms=1)
            self.make_cell(root, [future, canary])
            audit = live_cell(Path(root), "test", 1)
            self.assertFalse(audit["execution_complete"])
            self.assertIn("rejected_publication_nonzero", audit["findings"])


if __name__ == "__main__": unittest.main()
