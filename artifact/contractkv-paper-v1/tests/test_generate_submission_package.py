import unittest

from scripts.generate_submission_package import pct


class SubmissionPackageTests(unittest.TestCase):
    def test_percent_format(self):
        self.assertEqual(pct(0.32123), "32.12%")


if __name__ == "__main__":
    unittest.main()
