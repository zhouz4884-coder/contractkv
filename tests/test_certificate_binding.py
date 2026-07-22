import dataclasses
import unittest

from scripts.contractkv_certificate_binding import (
    CertificateBinding, RequestBinding, admitted, sign, validation_errors,
)


class CertificateBindingTests(unittest.TestCase):
    def setUp(self):
        self.secret = b"test-secret"
        self.binding = CertificateBinding(
            "contractkv.binding.v1", "cert-1", "model", "rev", "tok", "chat",
            "vllm", "runtime", "generation", "manifest", "policy", "*", "domain",
            "template", 1, "stable", "layout", 10)
        self.request = RequestBinding(
            "model", "rev", "tok", "chat", "vllm", "runtime", "generation",
            "manifest", "policy", "*", "domain", "template", 1, "stable", "layout", 2, True)

    def test_unseen_private_suffix_is_outside_binding(self):
        signature = sign(self.binding, self.secret)
        self.assertTrue(admitted(self.binding, self.request, signature, self.secret))

    def test_runtime_or_metadata_change_fails_closed(self):
        signature = sign(self.binding, self.secret)
        request = dataclasses.replace(self.request, runtime_revision="other")
        self.assertIn("runtime_revision_mismatch", validation_errors(
            self.binding, request, signature, self.secret))

    def test_private_suffix_cannot_be_published(self):
        signature = sign(self.binding, self.secret)
        request = dataclasses.replace(self.request, private_suffix_excluded=False)
        self.assertIn("private_suffix_not_excluded", validation_errors(
            self.binding, request, signature, self.secret))


if __name__ == "__main__":
    unittest.main()
