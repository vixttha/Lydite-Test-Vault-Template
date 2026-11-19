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
from urllib.error import HTTPError

from archive_manifest import load_manifest
from inventory import check_windows_paths, checkout_identity, execute_case, print_inventory, read_inventory, report_destination, run_cases, runtime_version
from native_outcomes import passed_tests
from validation_contract import lane_failure, validate_inventory
from release_record import (
    CandidateRejected, SUPPORTING_JOBS, fetch_support, github_resource, main as record_release, receipt_context,
    run_preflight, supporting_evidence, verify_candidate_target,
)


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

    def test_language_root_cannot_redirect_outside_inventory(self):
        test = self.add_language("one", "CHECK-001")
        folder = test.parent.parent
        with TemporaryDirectory() as target:
            external = Path(target) / "external"
            shutil.move(folder, external)
            try:
                folder.symlink_to(external, target_is_directory=True)
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"host cannot create a directory link: {error}")
            with self.assertRaisesRegex(ValueError, "language root must stay inside"):
                read_inventory(self.root)

    def test_upstream_coverage_checks_all_declared_tracks(self):
        inventory = read_inventory(Path(__file__).resolve().parents[1] / "languages")
        validate_inventory(inventory)
        inventory.pop("ruby")
        with self.assertRaisesRegex(ValueError, "ubuntu-24.04/ruby"):
            validate_inventory(inventory)

    def test_setup_failure_records_unstarted_runner_cases(self):
        record = lane_failure("windows-latest", "setup", {
            "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "11", "GITHUB_RUN_ATTEMPT": "2",
        })
        self.assertEqual(record["failed_stage"], "setup")
        self.assertEqual(record["attempt"], "2")
        self.assertEqual(record["cases"], [{"case_id": "POWERSHELL-001", "outcome": "NOT_RUN"}])

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

    def test_primary_and_support_fixtures_cannot_link_outside_tests(self):
        primary = self.add_language("one", "CHECK-001")
        outside = primary.parent.parent / "outside.py"
        outside.write_text("# External file\n", encoding="utf-8")
        support = primary.with_name("support.py")
        metadata = primary.parent.parent / "metadata.json"
        manifest = json.loads(metadata.read_text(encoding="utf-8"))
        manifest["cases"][0]["support"] = ["tests/support.py"]
        metadata.write_text(json.dumps(manifest), encoding="utf-8")
        try:
            support.symlink_to(outside)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"host cannot create symbolic links: {error}")
        with self.assertRaisesRegex(ValueError, "inside tests/.*support.py"):
            read_inventory(self.root)
        support.unlink()
        support.touch()
        self.assertEqual(set(read_inventory(self.root)), {"one"})
        primary.unlink()
        primary.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "inside tests/.*check.py"):
            read_inventory(self.root)

    def test_tests_root_cannot_be_a_directory_link(self):
        primary = self.add_language("one", "CHECK-001")
        tests = primary.parent
        external = tests.with_name("external")
        tests.rename(external)
        try:
            tests.symlink_to(external, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"host cannot create directory links: {error}")
        with self.assertRaisesRegex(ValueError, "real directory inside the language folder"):
            read_inventory(self.root)

    def test_windows_paths_reject_invalid_names_and_case_collisions(self):
        for paths in (["tests/a:b.py"], ["tests/CON.txt"], ["tests/a.py", "tests/A.py"],
                      ["tests/Sub/a.py", "tests/sub/b.py"]):
            with self.subTest(paths=paths), self.assertRaisesRegex(ValueError, "Windows .*fixture"):
                check_windows_paths(self.root, paths)
        check_windows_paths(self.root, ["tests/ok.py", "tests/sub/also-ok.py"])

    def test_inventory_table_escapes_pipes_and_collapses_newlines(self):
        self.add_language("one", "CHECK-001")
        manifests = read_inventory(self.root)
        manifests["one"].update(language="Python | CPython", runtime="Python 3.12\nRunner")
        output = io.StringIO()
        with redirect_stdout(output):
            print_inventory(manifests)
        self.assertIn(r"| Python \| CPython | Python 3.12 Runner | 1 | 1 | ubuntu-24.04 |", output.getvalue())

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
            {**base, "id": "CHECK-003", "test": "tests/second.py", "commands": [["python", "tests/second.py"]]},
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

    @unittest.skipUnless(shutil.which("node"), "Node is needed for TAP regression checks")
    def test_named_node_tests_decode_tap_escapes_without_hiding_directives(self):
        with TemporaryDirectory() as directory:
            test = Path(directory) / "fixture.test.mjs"
            for name, options, outcome in (
                ("fixes issue #42", "{}", "PASS"),
                ("includes # SKIP in the title", "{}", "PASS"),
                ("path uses \\ and #", "{}", "PASS"),
                ("skips a path ending in \\", "{skip: true}", "SKIP"),
                ("todo #42", "{todo: true}", "FAIL"),
            ):
                with self.subTest(name=name), redirect_stdout(io.StringIO()):
                    test.write_text(
                        "import { test } from 'node:test';\nimport assert from 'node:assert/strict';\n"
                        f"test({json.dumps(name)}, {options}, () => assert.equal(2 + 2, 4));\n"
                        "test('unrelated', () => assert.equal(3 + 4, 7));\n",
                        encoding="utf-8",
                    )
                    case = {"native_runner": "node-tap", "native_test": name, "test": test.name,
                            "commands": [["node", "--test", "--test-reporter=tap", str(test)]]}
                    self.assertEqual(execute_case(case, directory, os.environ)[0], outcome)
                    self.assertEqual(
                        execute_case({**case, "native_test": "missing"}, directory, os.environ)[0], "FAIL"
                    )

    @unittest.skipUnless(shutil.which("node"), "Node is needed for named test regression checks")
    def test_node_native_names_distinguish_newlines_and_literal_backslashes(self):
        with TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            test = Path(directory) / "fixture.test.mjs"
            actual, different = "line\nbreak", r"line\nbreak"
            test.write_text(f"import {{test}} from 'node:test';\ntest({json.dumps(actual)}, () => {{}});\n")
            case = {"native_runner": "node-tap", "test": test.name,
                    "commands": [["node", "--test", "--test-reporter=tap", str(test)]]}
            self.assertEqual(execute_case({**case, "native_test": actual}, directory, os.environ)[0], "PASS")
            self.assertEqual(execute_case({**case, "native_test": different}, directory, os.environ)[0], "FAIL")

    @unittest.skipUnless(shutil.which("node"), "Node is needed for named test regression checks")
    def test_node_native_names_preserve_whitespace(self):
        with TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            test = Path(directory) / "fixture.test.mjs"
            test.write_text("import {test} from 'node:test';\ntest(' name ', () => {});\n")
            case = {"native_runner": "node-tap", "test": test.name,
                    "commands": [["node", "--test", "--test-reporter=tap", str(test)]]}
            self.assertEqual(execute_case({**case, "native_test": " name "}, directory, os.environ)[0], "PASS")
            self.assertEqual(execute_case({**case, "native_test": "name"}, directory, os.environ)[0], "FAIL")

    @unittest.skipUnless(shutil.which("node"), "Node is needed for nested test regression checks")
    def test_node_native_paths_distinguish_identical_leaf_names(self):
        with TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            test = Path(directory) / "fixture.test.mjs"
            test.write_text(
                "import {describe, it} from 'node:test';\n"
                "describe('outer', () => describe('inner', () => it('leaf', () => {})));\n"
                "describe('other', () => it('leaf', {skip:true}, () => {}));\n"
            )
            case = {"native_runner": "node-tap", "test": test.name,
                    "commands": [["node", "--test", "--test-reporter=tap", str(test)]]}
            for name, expected in ((["outer", "inner", "leaf"], "PASS"),
                                   (["other", "leaf"], "SKIP"), ("leaf", "FAIL")):
                with self.subTest(name=name):
                    self.assertEqual(execute_case({**case, "native_test": name}, directory, os.environ)[0], expected)

    def test_unittest_wrapper_preserves_isolated_imports(self):
        with TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            test = Path(directory) / "isolated_fixture.py"
            test.write_text("import unittest\nclass TestCase(unittest.TestCase):\n    def test_one(self): pass\n")
            case = {"native_runner": "unittest", "test": test.name, "native_test": "TestCase.test_one"}
            for argv, expected in ((["-I"], "FAIL"), ([], "PASS")):
                command = [sys.executable, *argv, "-m", "unittest", "isolated_fixture"]
                self.assertEqual(execute_case({**case, "commands": [command]}, directory, os.environ)[0], expected)

    def test_unittest_wrapper_honors_failfast_and_buffer(self):
        with TemporaryDirectory() as directory:
            test = Path(directory) / "fixture.py"
            test.write_text(
                "import unittest\nclass Tests(unittest.TestCase):\n"
                "    def test_first(self): self.fail('controlled failure')\n"
                "    def test_second(self): print('second method ran')\n"
            )
            for args, expected, hidden in ((["-f"], "FAIL", "second method ran"),
                                           (["-b", "fixture.Tests.test_second"], "PASS", "second method ran")):
                command = [sys.executable, "-m", "unittest", *args]
                if len(args) == 1:
                    command.append("fixture")
                output = io.StringIO()
                case = {"native_runner": "unittest", "test": test.name,
                        "native_test": "Tests.test_second", "commands": [command]}
                with redirect_stdout(output):
                    self.assertEqual(execute_case(case, directory, os.environ)[0], expected)
                self.assertNotIn(hidden, output.getvalue())

    def test_unittest_records_passes_alongside_setup_and_subtest_skips(self):
        with TemporaryDirectory() as directory:
            test = Path(directory) / "test_fixture.py"
            case = {"native_runner": "unittest",
                    "commands": [[sys.executable, "-m", "unittest", "discover"]]}
            source = "import unittest\n"
            setup_skip = (
                "class Unavailable(unittest.TestCase):\n"
                "    @classmethod\n"
                "    def setUpClass(cls): raise unittest.SkipTest('optional dependency')\n"
                "    def test_unavailable(self): self.fail('unreachable')\n"
            )
            subtests = (
                "class Mixed(unittest.TestCase):\n"
                "    def test_mixed(self):\n"
                "        with self.subTest('optional'): self.skipTest('optional dependency')\n"
                "        with self.subTest('required'): self.assertEqual(2 + 2, 4)\n"
            )
            passing = "class Passing(unittest.TestCase):\n    def test_pass(self): self.assertTrue(True)\n"
            for content, wanted in ((passing + setup_skip, "PASS"), (subtests, "SKIP"),
                                    (setup_skip, "SKIP"), ("", "FAIL")):
                with self.subTest(wanted=wanted), redirect_stdout(io.StringIO()):
                    test.write_text(source + content, encoding="utf-8")
                    self.assertEqual(execute_case(case, directory, os.environ)[0], wanted)

    def test_named_unittest_reports_skip_after_passing_subtest(self):
        with TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            test = Path(directory) / "fixture.py"
            test.write_text(
                "import unittest\nclass Tests(unittest.TestCase):\n"
                "    def test_mixed(self):\n"
                "        with self.subTest('passes'): self.assertTrue(True)\n"
                "        with self.subTest('skips'): self.skipTest('optional')\n"
            )
            case = {"native_runner": "unittest", "test": test.name, "native_test": "Tests.test_mixed",
                    "commands": [[sys.executable, "-m", "unittest", "fixture"]]}
            self.assertEqual(execute_case(case, directory, os.environ)[0], "SKIP")

    def test_named_unittest_matches_class_setup_skip_to_loaded_methods(self):
        with TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            test = Path(directory) / "fixture.py"
            test.write_text(
                "import unittest\nclass Tests(unittest.TestCase):\n"
                "    @classmethod\n"
                "    def setUpClass(cls): raise unittest.SkipTest('optional')\n"
                "    def test_selected(self): pass\n"
                "    def test_unselected(self): pass\n"
            )
            case = {"native_runner": "unittest", "test": test.name,
                    "commands": [[sys.executable, "-m", "unittest", "fixture.Tests.test_selected"]]}
            for name, expected in (("Tests.test_selected", "SKIP"), ("Tests.test_unselected", "FAIL")):
                self.assertEqual(execute_case({**case, "native_test": name}, directory, os.environ)[0], expected)

    def test_unittest_cleanup_output_does_not_hide_the_named_result(self):
        with TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            test = Path(directory) / "fixture.py"
            test.write_text(
                "import atexit, unittest\natexit.register(print, 'cleanup')\n"
                "class Tests(unittest.TestCase):\n    def test_pass(self): pass\n"
            )
            case = {"native_runner": "unittest", "test": test.name, "native_test": "Tests.test_pass",
                    "commands": [[sys.executable, "-m", "unittest", "fixture"]]}
            self.assertEqual(execute_case(case, directory, os.environ)[0], "PASS")

    def test_named_unittest_must_run_from_the_declared_file(self):
        with TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            folder = Path(directory)
            tests = folder / "tests"
            tests.mkdir()
            fixture = (
                "import unittest\nclass Fixture(unittest.TestCase):\n"
                "    def test_expected(self): self.assertTrue(True)\n"
                "    def test_other(self): self.assertTrue(True)\n"
            )
            for name in ("primary", "unrelated"):
                (tests / f"{name}.py").write_text(fixture, encoding="utf-8")
            command = [sys.executable, "-m", "unittest", "discover", "-s", "tests"]
            case = {"test": "tests/primary.py", "native_runner": "unittest",
                    "native_test": "Fixture.test_expected"}
            for selector, method, wanted in (
                ("unrelated.py", "test_expected", "FAIL"),
                ("primary.py", "test_other", "FAIL"),
                ("primary.py", "test_expected", "PASS"),
            ):
                with self.subTest(selector=selector, method=method):
                    candidate = {**case, "commands": [[*command, "-p", selector, "-k", method]]}
                    self.assertEqual(execute_case(candidate, folder, os.environ)[0], wanted)


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

    def test_native_stage_survives_successful_post_processing(self):
        with TemporaryDirectory() as directory:
            test_file = Path(directory) / "test_contract.py"
            test_file.write_text(
                "import unittest\nclass Contract(unittest.TestCase):\n"
                "    def test_contract(self): self.assertEqual(2 + 2, 4)\n",
                encoding="utf-8",
            )
            build = [sys.executable, "-c", "pass"]
            suite = [sys.executable, "-m", "unittest", "-v", "test_contract"]
            cleanup = [sys.executable, "-c", "print('clean')"]
            case = {"commands": [build, suite, cleanup], "native_runner": "unittest", "native_command_index": 1}
            with redirect_stdout(io.StringIO()):
                self.assertEqual(execute_case(case, directory, os.environ)[0], "PASS")
                for stage in range(3):
                    commands = case["commands"].copy()
                    commands[stage] = [sys.executable, "-c", "raise SystemExit(3)"]
                    self.assertEqual(execute_case({**case, "commands": commands}, directory, os.environ)[0], "FAIL")

    def test_receipt_preserves_plan_and_reports_short_circuiting(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "languages/fixture").mkdir(parents=True)
            output = root / "evidence.json"
            stages = [[sys.executable, "-c", "raise SystemExit(5)"], [sys.executable, "-c", "pass"]]
            case = {"id": "STAGES-001", "purpose": "distinguish stages", "test": "tests/sample.py", "commands": stages}
            manifest = {"cases": [case], "runner": "ubuntu-24.04", "runtime": "Python"}
            with patch("inventory.ROOT", root), patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}):
                for code, outcomes in ((1, ["FAIL", "NOT_RUN"]), (0, ["PASS", "PASS"])):
                    with redirect_stdout(io.StringIO()):
                        self.assertEqual(run_cases({"fixture": manifest}, ["fixture"], output), code)
                    record = json.loads(output.read_text(encoding="utf-8"))["cases"][0]
                    self.assertEqual(record["commands"], stages)
                    self.assertEqual([stage["outcome"] for stage in record["command_results"]], outcomes)
                    self.assertEqual([stage["exit_code"] for stage in record["command_results"]],
                                     [5, None] if code else [0, 0])
                    stages[0][-1] = "pass"

    def test_runtime_probe_requires_nonblank_output(self):
        with TemporaryDirectory() as directory:
            for source, expected in (
                ("print(' ')", None),
                ("print('\\nRuntime 1.0')", "Runtime 1.0"),
                ("import sys; print(' '); print('Runtime 2.0', file=sys.stderr)", "Runtime 2.0"),
            ):
                with self.subTest(expected=expected):
                    self.assertEqual(runtime_version([sys.executable, "-c", source], directory, os.environ), expected)


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


    def test_report_rejects_new_files_inside_input_paths(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("inventory.ROOT", root), patch("inventory.execute_case") as execute:
                for path in (root / "languages" / "new.json", root / "tools" / "new.json"):
                    with self.assertRaisesRegex(ValueError, "inside project inputs"):
                        run_cases({}, [], path)
                execute.assert_not_called()

    def test_report_protects_linked_worktree_git_paths(self):
        with TemporaryDirectory() as directory:
            base = Path(directory)
            root, linked = base / "source", base / "linked"
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            git = ["git", "-C", str(root)]
            subprocess.run([*git, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                            "commit", "--allow-empty", "-qm", "fixture"], check=True)
            subprocess.run([*git, "worktree", "add", "--detach", "-q", str(linked)], check=True)
            with patch("inventory.ROOT", linked):
                for path in (root / ".git", root / ".git/worktrees/linked"):
                    with self.assertRaisesRegex(ValueError, "inside project inputs"):
                        report_destination(path / "report.json")
                self.assertEqual(report_destination(base / "report.json"), base / "report.json")

    def test_report_preflight_rejects_directory_and_file_parent(self):
        with TemporaryDirectory() as directory:
            base = Path(directory)
            parent = base / "file"
            parent.touch()
            with patch("inventory.ROOT", base / "project"), patch("inventory.execute_case") as execute:
                for path in (base, parent / "report.json"):
                    with self.assertRaisesRegex(ValueError, "filename with a directory parent"):
                        run_cases({}, [], path)
                execute.assert_not_called()

    def test_report_rejects_tracked_destinations_before_running_cases(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            tracked = root / "README.md"
            tracked.write_text("retained", encoding="utf-8")
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "add", "README.md"], check=True)
            fixture = {"cases": [{"id": "OUTPUT-001", "purpose": "Preserve inputs", "test": "tests/sample.py",
                                  "commands": [[sys.executable, "-c", "pass"]]}],
                       "runtime": "Python", "runner": "ubuntu-24.04"}
            with patch("inventory.ROOT", root), patch("inventory.execute_case") as execute:
                with self.assertRaisesRegex(ValueError, "tracked project file"):
                    run_cases({"fixture": fixture}, ["fixture"], tracked)
                execute.assert_not_called()
                alias = root / "docs-alias"
                try:
                    alias.symlink_to(tracked)
                except (OSError, NotImplementedError):
                    alias = tracked.parent / "." / tracked.name
                with self.assertRaisesRegex(ValueError, "tracked project file"):
                    report_destination(alias)
                self.assertEqual(report_destination(root / "run.json"), (root / "run.json").resolve())
            self.assertEqual(tracked.read_text(encoding="utf-8"), "retained")


class ReleaseEvidenceTests(unittest.TestCase):
    def test_archive_manifest_rejects_nested_duplicate_keys(self):
        with self.assertRaisesRegex(ValueError, "duplicate archive manifest field"):
            load_manifest('{"versions":{"v0.0.1":{"source_commit":"a","source_commit":"b"}}}')

    def test_archive_manifest_rejects_boolean_schema(self):
        with self.assertRaisesRegex(ValueError, "schema_version must be integer"):
            load_manifest('{"schema_version":true}')
        self.assertEqual(load_manifest('{"schema_version":1}'), {"schema_version": 1})

    def test_github_state_treats_only_expected_not_found_as_missing(self):
        for status in (403, 404, 429, 503):
            with self.subTest(status=status), patch.dict(os.environ, {"GITHUB_API_URL": "https://example.invalid"}):
                failure = HTTPError("https://example.invalid", status, "fixture", {}, None)
                with patch("release_record.urlopen", side_effect=failure):
                    if status == 404:
                        self.assertIsNone(github_resource("tag", allow_missing=True))
                    else:
                        with self.assertRaisesRegex(ValueError, f"HTTP {status}"):
                            github_resource("tag", allow_missing=True)
                if status == 404:
                    with patch("release_record.urlopen", side_effect=failure):
                        with self.assertRaisesRegex(ValueError, "HTTP 404"):
                            github_resource("required commit")

    def test_fresh_candidate_requires_a_visible_checkout(self):
        checkout = "a" * 40
        with patch("release_record.github_resource", side_effect=[None, None, {"sha": checkout}]) as read:
            verify_candidate_target("example/vault", "v1.2.3", checkout)
        self.assertEqual([call.args[0] for call in read.call_args_list], [
            "repos/example/vault/releases/tags/v1.2.3", "repos/example/vault/git/ref/tags/v1.2.3",
            f"repos/example/vault/git/commits/{checkout}",
        ])
        with patch("release_record.github_resource", side_effect=[None, None, {"sha": "b" * 40}]):
            with self.assertRaisesRegex(ValueError, "wrong object"):
                verify_candidate_target("example/vault", "v1.2.3", checkout)

    def test_published_release_and_conflicting_tag_are_rejected(self):
        checkout = "a" * 40
        with patch("release_record.github_resource", return_value={"tag_name": "v1.2.3", "draft": False}):
            with self.assertRaisesRegex(ValueError, "already published"):
                verify_candidate_target("example/vault", "v1.2.3", checkout)
        ref = {"ref": "refs/tags/v1.2.3", "object": {"type": "commit", "sha": "b" * 40}}
        with patch("release_record.github_resource", side_effect=[None, ref]):
            with self.assertRaisesRegex(ValueError, "not the validated checkout"):
                verify_candidate_target("example/vault", "v1.2.3", checkout)

    def test_matching_unpublished_lightweight_and_annotated_tags_are_accepted(self):
        checkout = "a" * 40
        commit = {"type": "commit", "sha": checkout}
        tag = {"type": "tag", "sha": "b" * 40}
        draft = {"tag_name": "v1.2.3", "draft": True}
        for target, remaining in ((commit, []), (tag, [{"object": commit}])):
            with patch("release_record.github_resource", side_effect=[
                draft, {"ref": "refs/tags/v1.2.3", "object": target}, *remaining,
            ]):
                verify_candidate_target("example/vault", "v1.2.3", checkout)
        with patch("release_record.github_resource", side_effect=[
            None, {"ref": "refs/tags/v1.2.3", "object": tag}, {"object": tag},
        ]):
            with self.assertRaisesRegex(ValueError, "Could not resolve tag"):
                verify_candidate_target("example/vault", "v1.2.3", checkout)

    def test_preflight_and_receipt_check_current_release_state(self):
        checkout = "a" * 40
        environment = {
            "GITHUB_SHA": checkout, "GITHUB_REPOSITORY": "example/vault",
            "GITHUB_EVENT_NAME": "workflow_dispatch", "LYDITE_RELEASE_VERSION": "v1.2.3",
            "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SERVER_URL": "https://example.invalid",
        }
        support = [{"artifact": {"expires_at": "2026-12-19T00:00:00Z"}}]
        with TemporaryDirectory() as folder, patch.dict(os.environ, environment, clear=True), \
                patch("release_record.git", side_effect=lambda *args: (
                    '{"schema_version":1,"current":"v0.0.3","versions":{"v0.0.3":{}}}' if args[0] == "show" else checkout
                )) as source, \
                patch("release_record.fetch_support", return_value=support) as fetch, \
                patch("release_record.verify_candidate_target") as verify, redirect_stdout(io.StringIO()):
            with patch.object(sys, "argv", ["release_record.py", "--check-target"]):
                record_release()
            verify.assert_called_once_with("example/vault", "v1.2.3", checkout)
            fetch.assert_not_called()
            output = Path(folder) / "receipt.json"
            with patch.object(sys, "argv", ["release_record.py", str(output)]):
                verify.side_effect = ValueError("v1.2.3 is already published")
                with self.assertRaisesRegex(SystemExit, "already published"):
                    record_release()
                self.assertFalse(output.exists())
                verify.side_effect = None
                record_release()
            record = json.loads(output.read_bytes())
            self.assertEqual(record["target"], "v1.2.3")
            self.assertEqual(record["archive_current"], "v0.0.3")
            source.assert_any_call("show", f"{checkout}:versions/manifest.json")

    def test_preflight_records_distinct_rejections_without_candidate_receipt(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {
            "GITHUB_EVENT_NAME": "workflow_dispatch", "LYDITE_RELEASE_VERSION": "v1.2.3",
            "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "42", "GITHUB_RUN_ATTEMPT": "2",
        }, clear=True):
            target = Path(directory) / "preflight.json"
            for failure, reason in ((CandidateRejected("published", "already published"), "published"),
                                    (CandidateRejected("tag_conflict", "different commit"), "tag_conflict"),
                                    (ValueError("GitHub unavailable"), "unavailable")):
                with patch("release_record.verify_candidate_target", side_effect=failure):
                    with self.assertRaises(SystemExit):
                        run_preflight("example/vault", "a" * 40, target)
                result = json.loads(target.read_bytes())
                self.assertEqual((result["kind"], result["outcome"], result["reason"], result["attempt"]),
                                 ("named-candidate-preflight", "REJECTED", reason, "2"))
            with patch.dict(os.environ, {"LYDITE_RELEASE_VERSION": "invalid"}):
                with self.assertRaisesRegex(SystemExit, "invalid_target"):
                    run_preflight("example/vault", "a" * 40, target)

    def test_routine_validation_has_no_release_identity(self):
        self.assertEqual(receipt_context("pull_request", pr_head="head", pr_base="base"), {
            "kind": "validation", "event": "pull_request",
            "pull_request_head": "head", "pull_request_base": "base",
        })
        self.assertEqual(receipt_context("workflow_dispatch")["kind"], "validation")
        with self.assertRaisesRegex(ValueError, "explicit workflow dispatch"):
            receipt_context("pull_request", "v1.2.3")

    def test_explicit_dispatch_binds_a_valid_release_target(self):
        context = receipt_context("workflow_dispatch", "v1.2.3")
        self.assertEqual(context["kind"], "release_candidate")
        self.assertEqual(context["target"], "v1.2.3")
        self.assertEqual(context["publication_state"], "awaiting-owner-approval")
        with self.assertRaisesRegex(ValueError, "vMAJOR.MINOR.PATCH"):
            receipt_context("workflow_dispatch", "main")

    def test_paginated_lookup_reads_current_attempt_and_reports_missing(self):
        jobs = [{"name": name, "id": index, "run_id": 1, "run_attempt": 26, "conclusion": "success"}
                for index, (name, _) in enumerate(SUPPORTING_JOBS, 1)]
        current = [{"name": f"{prefix}-attempt-26", "id": index, "expired": False,
                    "expires_at": "2026-12-19T00:00:00Z", "digest": "sha256:fixture"}
                   for index, (_, prefix) in enumerate(SUPPORTING_JOBS, 1) if prefix]
        previous = [{"name": f"prior-{index}", "id": index + 100, "expired": False} for index in range(100)]
        def response(args, text):
            self.assertIn("--paginate", args)
            if "/jobs?" in args[-1]:
                return json.dumps({"jobs": jobs})
            return json.dumps({"artifacts": previous}) + "\n" + json.dumps({"artifacts": current})
        with patch("release_record.subprocess.check_output", side_effect=response), patch("release_record.time.sleep"):
            self.assertEqual(len(fetch_support("example/vault", 1, 26, "url")), len(SUPPORTING_JOBS))
            current.pop()
            with self.assertRaisesRegex(ValueError, "unavailable or incomplete"):
                fetch_support("example/vault", 1, 26, "url")

    def test_receipt_requires_a_complete_same_attempt_evidence_set(self):
        attempt, run_id = 2, 123
        jobs = [{"name": name, "id": index, "run_id": run_id, "run_attempt": attempt, "conclusion": "success"}
                for index, (name, _) in enumerate(SUPPORTING_JOBS, 1)]
        artifacts = [{"name": f"{prefix}-attempt-2", "id": index, "expired": False,
                      "expires_at": "2026-12-19T00:00:00Z", "digest": "sha256:fixture"}
                     for index, (_, prefix) in enumerate(SUPPORTING_JOBS, 1) if prefix]

        def verify():
            return supporting_evidence(jobs, artifacts, run_id, attempt, "https://example.invalid/runs/123")

        self.assertEqual([item["artifact"]["id"] for item in verify() if "artifact" in item], [1, 2, 3])
        jobs[0]["run_attempt"] = 1
        with self.assertRaisesRegex(ValueError, "attempt 2.*Re-run all jobs"):
            verify()
        jobs[0]["run_attempt"] = attempt
        artifacts[0]["name"] = "lydite-adoption-attempt-1"
        with self.assertRaisesRegex(ValueError, "lydite-adoption-attempt-2.*Re-run all jobs"):
            verify()
        artifacts[0]["name"] = "lydite-adoption-attempt-2"
        artifacts[0]["expired"] = True
        with self.assertRaisesRegex(ValueError, "unavailable or incomplete"):
            verify()
