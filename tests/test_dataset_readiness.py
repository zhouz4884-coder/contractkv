import unittest

from scripts.prepare_dataset_samples import (
    DATASET_READINESS_FIELDS,
    dataset_readiness_row,
    hf_cache_is_on_large_disk,
)


class DatasetReadinessTests(unittest.TestCase):
    def test_readiness_schema_is_fixed(self):
        self.assertEqual(
            DATASET_READINESS_FIELDS,
            [
                "dataset",
                "source_zip",
                "source_present",
                "repo_extracted",
                "data_available",
                "prepare_method",
                "sample_count",
                "status",
                "source_note",
                "hf_cache_dir",
                "error_type",
                "error_message",
            ],
        )

    def test_hf_cache_must_point_to_large_disk(self):
        self.assertTrue(
            hf_cache_is_on_large_disk(
                "/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/datasets/hf_cache"
            )
        )
        self.assertFalse(hf_cache_is_on_large_disk("/home/user/.cache/huggingface"))

    def test_bfcl_missing_optional_row_is_nonblocking(self):
        row = dataset_readiness_row(
            dataset="BFCL",
            source_zip="",
            source_present=False,
            repo_extracted=False,
            data_available=False,
            prepare_method="not_downloaded",
            sample_count=0,
            status="missing_optional",
            source_note="BFCL missing_optional",
            hf_cache_dir="",
            error_type="missing_optional",
            error_message="BFCL is not part of characterization_batch_001",
        )

        self.assertEqual(row["status"], "missing_optional")
        self.assertEqual(row["sample_count"], 0)


if __name__ == "__main__":
    unittest.main()
