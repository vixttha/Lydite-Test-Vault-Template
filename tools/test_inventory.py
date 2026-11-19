import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from inventory import read_inventory
from native_outcomes import passed_tests


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


class NativeOutcomeTests(unittest.TestCase):
    def test_native_results_require_a_positive_pass_count(self):
        reports = {
            "go-json": (
                '{"Action":"pass","Test":"TestBound"}',
                '{"Action":"pass","Package":"pkg"}',
                '{"Action":"skip","Test":"TestBound"}',
            ),
            "node-tap": ("# pass 1\n", "# pass 0\n", "# pass 0\n# skipped 1\n"),
            "rust-libtest": (
                "test result: ok. 1 passed; 0 failed;",
                "test result: ok. 0 passed; 0 failed;",
                "test result: ok. 0 passed; 0 failed; 1 ignored;",
            ),
            "unittest": (
                "Ran 1 test in 0.001s\n\nOK\n",
                "Ran 0 tests in 0.001s\n\nOK\n",
                "Ran 1 test in 0.001s\n\nOK (skipped=1)\n",
            ),
        }
        for runner, (passing, empty, skipped) in reports.items():
            with self.subTest(runner=runner):
                self.assertEqual(passed_tests(runner, passing), 1)
                self.assertEqual(passed_tests(runner, empty), 0)
                self.assertEqual(passed_tests(runner, skipped), 0)
