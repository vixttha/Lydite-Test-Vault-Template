import io
import json
import unittest
import zipfile

from supporting_payloads import read_documents, sha256, verify_payload


class PayloadTests(unittest.TestCase):
    def test_downloaded_zip_digest_is_checked(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as bundle:
            bundle.writestr("examples.json", json.dumps({"fixture": True}))
        data = stream.getvalue()
        self.assertEqual(read_documents(data, f"sha256:{sha256(data)}"), {"examples.json": {"fixture": True}})
        with self.assertRaisesRegex(ValueError, "ZIP digest differs"):
            read_documents(data, "sha256:" + "0" * 64)

    def test_runner_payload_requires_checkout_attempt_and_real_passing_cases(self):
        scope = {"schema_version": 1, "checkout_sha": "a" * 40, "run_id": "123", "attempt": "7"}
        row = {"case_id": "POWERSHELL-001", "language": "powershell", "outcome": "PASS",
               "declared_runner": "windows-latest"}
        report = {**scope, "source": {"state": "CLEAN", "commit": "a" * 40, "base_commit": "a" * 40},
                  "runner": "windows-latest", "cases": [row]}
        runner = "lydite-cases-windows-latest"
        verify_payload({"examples.json": report}, runner, scope, {})
        for changed in ({"checkout_sha": "b" * 40}, {"attempt": "6"}, {"cases": []},
                        {"cases": [{**row, "outcome": "BLOCKED"}]},
                        {"cases": [row, row]}, {"runner": "ubuntu-24.04"}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                verify_payload({"examples.json": {**report, **changed}}, runner, scope, {})
