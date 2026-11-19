import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from inventory import read_inventory


class InventoryTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def add_language(self, slug, case_id):
        folder = self.root / slug
        tests = folder / "tests"
        tests.mkdir(parents=True)
        test = tests / "check.py"
        test.write_text("# Example test\n", encoding="utf-8")
        (folder / "GUIDE.md").write_text("# Guide\n", encoding="utf-8")
        manifest = {
            "schema_version": 1,
            "language": slug,
            "runtime": "Python 3.12",
            "runner": "ubuntu-24.04",
            "cases": [{
                "id": case_id,
                "purpose": "Example contract",
                "test": "tests/check.py",
                "support": [],
                "commands": [["python", "tests/check.py"]],
            }],
        }
        (folder / "metadata.json").write_text(json.dumps(manifest), encoding="utf-8")
        return test

    def test_valid_manifest_and_fixture_are_reported(self):
        self.add_language("one", "CHECK-001")
        self.assertEqual(set(read_inventory(self.root)), {"one"})

    def test_deleted_or_unlisted_files_fail_validation(self):
        test = self.add_language("one", "CHECK-001")
        test.rename(test.with_name("renamed.py"))
        with self.assertRaisesRegex(ValueError, "missing.*check.py.*unlisted.*renamed.py"):
            read_inventory(self.root)

    def test_duplicate_case_id_across_languages_fails(self):
        self.add_language("one", "CHECK-001")
        self.add_language("two", "CHECK-001")
        with self.assertRaisesRegex(ValueError, "duplicate case CHECK-001"):
            read_inventory(self.root)
