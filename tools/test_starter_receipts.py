import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


class CopiedReceiptTests(unittest.TestCase):
    def test_copied_receipt_extension_is_case_sensitive_on_each_runner(self):
        starter = Path(__file__).resolve().parents[1] / "starter/test-vault"
        with patch.object(sys, "path", [str(starter), *sys.path]):
            from verify_receipts import verdict
        expected = {
            "schema_version": 2, "case_id": "DOCS-001", "checkout_sha": "a" * 40,
            "run_id": "1", "attempt": "1", "evidence_sha256": None, "case_plan_sha256": "b" * 64,
        }
        row = {**expected, "check_id": "sample", "status": "pass",
               "environment": {"os": sys.platform, "runtime": "Python"}}
        with TemporaryDirectory() as folder:
            directory = Path(folder)
            filename = directory / "sample.JSON"
            filename.write_text(json.dumps(row), encoding="utf-8")
            self.assertEqual(verdict(directory, ["sample"], expected)[0][0][1], "MISSING")
            filename.unlink()
            (directory / "sample.json").write_text(json.dumps(row), encoding="utf-8")
            self.assertEqual(verdict(directory, ["sample"], expected)[0][0][1], "PASS")
