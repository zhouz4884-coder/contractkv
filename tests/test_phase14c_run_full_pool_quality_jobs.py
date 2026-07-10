from __future__ import annotations

import unittest

from scripts.phase14c_run_full_pool_quality_jobs import (
    build_labels,
    completed_job_ids,
    quality_messages,
    select_pending_jobs,
    summarize_labels,
)


class Phase14CFullPoolQualityRunnerTests(unittest.TestCase):
    def test_select_pending_jobs_filters_done_partition_policy_and_limit(self):
        jobs = [
            {"job_id": "a", "partition": "calibration", "policy": "raw-order"},
            {"job_id": "b", "partition": "held_out_quality", "policy": "raw-order"},
            {"job_id": "c", "partition": "calibration", "policy": "contractkv-caposc"},
        ]
        selected = select_pending_jobs(jobs, {"a"}, {"calibration"}, {"contractkv-caposc"}, max_jobs=1)
        self.assertEqual([job["job_id"] for job in selected], ["c"])

    def test_completed_job_ids_uses_existing_raw_rows(self):
        self.assertEqual(completed_job_ids([{"job_id": "a"}, {"job_id": ""}, {}]), {"a"})

    def test_build_labels_computes_drop_and_false_safe(self):
        raw_rows = [
            {"sample_key": "s", "policy": "raw-order", "score": 1.0, "success": True, "partition": "calibration", "dataset": "LongBench", "task": "qasper", "sample_id": "0", "request_id": "r"},
            {"sample_key": "s", "policy": "contractkv-caposc", "score": 0.9, "success": True, "partition": "calibration", "dataset": "LongBench", "task": "qasper", "sample_id": "0", "request_id": "c"},
        ]
        features = [{"sample_key": "s", "qc_prelabel_fallback": False, "partition": "calibration"}]
        labels = build_labels(raw_rows, features, eps=0.03)
        self.assertEqual(len(labels), 1)
        self.assertTrue(labels[0]["unsafe_quality_drop"])
        self.assertTrue(labels[0]["false_safe"])

    def test_summary_reports_gate_metrics_over_completed_labels(self):
        labels = [
            {"partition": "calibration", "dataset": "LongBench", "task": "hotpotqa", "unsafe_quality_drop": False, "qc_prelabel_fallback": False, "safe_optimization": True, "false_safe": False, "quality_drop_vs_raw": 0.0, "raw_success": True, "candidate_success": True},
            {"partition": "calibration", "dataset": "LongBench", "task": "qasper", "unsafe_quality_drop": True, "qc_prelabel_fallback": True, "safe_optimization": False, "false_safe": False, "quality_drop_vs_raw": 0.1, "raw_success": True, "candidate_success": True},
        ]
        summary = summarize_labels(labels)
        all_row = next(row for row in summary if row["split"] == "all")
        self.assertEqual(all_row["requests"], 2)
        self.assertEqual(all_row["unsafe_requests"], 1)
        self.assertEqual(all_row["false_safe_rate"], 0.0)

    def test_quality_messages_do_not_include_policy_name(self):
        case = {"dataset": "LongBench", "task": "hotpotqa", "sample_id": "0"}
        messages = quality_messages(case, "compiled text")
        joined = "\n".join(message["content"] for message in messages)
        self.assertIn("PHASE14C:LongBench:hotpotqa:0", joined)
        self.assertNotIn("raw-order", joined)
        self.assertNotIn("contractkv-caposc", joined)


if __name__ == "__main__":
    unittest.main()
