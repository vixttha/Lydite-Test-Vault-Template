from contextlib import redirect_stdout
import io
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from tempfile import TemporaryDirectory

from inventory import checkout_identity, execute_case, print_inventory, read_inventory, run_cases
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

    def test_metadata_rejects_bad_types_and_duplicate_keys_with_context(self):
        self.add_language("one", "CHECK-001")
        path = self.root / "one" / "metadata.json"
        valid = path.read_text(encoding="utf-8")
        for mutation, diagnosis in (
            (valid.replace('"schema_version": 1', '"schema_version": true'), "schema_version"),
            (valid.replace('"Example contract"', 'null'), "CHECK-001: purpose"),
            (valid.replace('"runner":', '"runner": "ubuntu-24.04", "runner":'), "duplicate JSON field"),
        ):
            with self.subTest(diagnosis=diagnosis):
                path.write_text(mutation, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, f"metadata.json: .*{diagnosis}"):
                    read_inventory(self.root)

    def test_case_paths_are_normalized_before_counting(self):
        test = self.add_language("one", "CHECK-001")
        fixture = test.with_name("fixture.txt")
        fixture.touch()
        test.with_name("second.py").touch()
        path = self.root / "one" / "metadata.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        base = manifest["cases"][0]
        manifest["cases"] += [
            {**base, "id": "CHECK-002", "test": "tests/./check.py", "support": ["tests/./fixture.txt"]},
            {**base, "id": "CHECK-003", "test": "tests/second.py"},
        ]
        path.write_text(json.dumps(manifest), encoding="utf-8")
        output = io.StringIO()
        with redirect_stdout(output):
            print_inventory(read_inventory(self.root))
        self.assertIn("| 3 | 2 |", output.getvalue())


class NativeOutcomeTests(unittest.TestCase):
    def test_native_results_require_a_positive_pass_count(self):
        reports = {
            "go-json": (
                '{"Action":"pass","Test":"TestBound"}',
                '{"Action":"pass","Package":"pkg"}',
                '{"Action":"skip","Test":"TestBound"}',
            ),
            "node-tap": ("ok 1 - passing test\n", "1..0\n", "ok 1 - skipped test # SKIP\n"),
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

    @unittest.skipUnless(shutil.which("node"), "Node is needed for TAP regression checks")
    def test_node_tap_checks_leaf_results_instead_of_parent_groups(self):
        with TemporaryDirectory() as directory:
            test = Path(directory) / "fixture.test.mjs"
            for statement, wanted in (
                ("await t.test('optional', {skip: true}, () => {});", "SKIP"),
                ("await t.test('required', () => assert.equal(2 + 2, 4));", "PASS"),
                ("await t.test('todo', {todo: true}, () => {});", "FAIL"),
            ):
                with self.subTest(statement=statement), redirect_stdout(io.StringIO()):
                    test.write_text(
                        "import { test } from 'node:test';\nimport assert from 'node:assert/strict';\n"
                        + "test('group', async (t) => {" + statement + "});\n",
                        encoding="utf-8",
                    )
                    case = {"native_runner": "node-tap",
                            "commands": [["node", "--test", "--test-reporter=tap", str(test)]]}
                    self.assertEqual(execute_case(case, directory, os.environ)[0], wanted)


class CommandOutcomeTests(unittest.TestCase):
    def test_failure_timeout_and_missing_executable_have_distinct_outcomes(self):
        commands = [
            ([sys.executable, "-c", "raise SystemExit(3)"], "FAIL", "code 3", 10),
            ([sys.executable, "-c", "import time; time.sleep(10)"], "FAIL", "timed out", 0.1),
            (["lydite-fixture-missing-executable"], "BLOCKED", "unavailable", 10),
        ]
        with TemporaryDirectory() as directory:
            for command, status, reason, timeout in commands:
                with self.subTest(command=command):
                    actual, detail = execute_case({"commands": [command]}, directory, os.environ, timeout=timeout)
                    self.assertEqual(actual, status)
                    self.assertIn(reason, detail)


class CheckoutIdentityTests(unittest.TestCase):
    def test_exact_identity_requires_clean_inputs_and_the_intended_root(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            git = ["git", "-C", directory]
            self.assertEqual(checkout_identity(root)["state"], "UNVERSIONED")
            subprocess.run([*git, "init", "-q"], check=True)
            test = root / "fixture.py"
            test.write_text("assert True\n", encoding="utf-8")
            subprocess.run([*git, "add", "."], check=True)
            subprocess.run(
                [*git, "-c", "user.name=Test Vault Fixture", "-c", "user.email=fixture@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "-qm", "Record fixture"],
                check=True,
            )
            clean = checkout_identity(root)
            self.assertEqual(clean["state"], "CLEAN")
            self.assertEqual(clean["commit"], clean["base_commit"])
            test.write_text("assert False\n", encoding="utf-8")
            self.assertEqual(checkout_identity(root), {
                "state": "MODIFIED", "commit": None, "base_commit": clean["commit"],
            })
            nested = root / "extracted-vault"
            nested.mkdir()
            self.assertEqual(checkout_identity(nested)["state"], "UNVERSIONED")


    def test_mid_run_drift_blocks_the_next_case_and_invalidates_the_sha(self):
        with TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "project"
            language = root / "languages" / "fixture"
            language.mkdir(parents=True)
            (language / "tracked.txt").write_text("original", encoding="utf-8")
            git = ["git", "-C", str(root)]
            subprocess.run([*git, "init", "-q"], check=True)
            subprocess.run([*git, "add", "."], check=True)
            subprocess.run(
                [*git, "-c", "user.name=Lydite Fixture", "-c", "user.email=fixture@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "-qm", "Fixture source"],
                check=True,
            )
            cases = [{
                "id": ident, "purpose": "Check checkout continuity", "test": "tests/example.py",
                "commands": [[sys.executable, "-c", command]],
            } for ident, command in (
                ("DRIFT-001", "from pathlib import Path; Path('tracked.txt').write_text('changed')"),
                ("DRIFT-002", "from pathlib import Path; Path('next-case-marker').touch()"),
            )]
            manifest = {"cases": cases, "runner": "ubuntu-24.04", "runtime": "Python"}
            evidence = base / "evidence.json"
            with patch("inventory.ROOT", root), redirect_stdout(io.StringIO()):
                result = run_cases({"fixture": manifest}, ["fixture"], evidence)
            report = json.loads(evidence.read_text(encoding="utf-8"))
            self.assertEqual(result, 1)
            self.assertIsNone(report["checkout_sha"])
            self.assertEqual(report["source"]["state"], "DRIFTED")
            self.assertEqual([row["outcome"] for row in report["cases"]], ["FAIL", "BLOCKED"])
            self.assertFalse((language / "next-case-marker").exists())
