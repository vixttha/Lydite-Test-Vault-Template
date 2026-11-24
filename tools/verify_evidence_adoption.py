"""Exercise opt-in v0.0.3 receipt checks in an existing v0.0.2 project."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from verify_adoption import ACTION, DIVIDER, HEADER, ROOT, STARTER, VALIDATOR, run


CASE_ROW = "| CLI-001 | CLI quote | P0 | Node.js and Python | Three units at 125 cents total 375 cents. |\n"
EXAMPLE = Path("test-vault/examples/shared-evidence")


def write_json(path, payload):
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def test_receipts(project, env, command, directory, observation):
    quiet_env = {key: value for key, value in env.items() if key != "GITHUB_STEP_SUMMARY"}
    original = {path: path.read_bytes() for path in directory.glob("*.json")}
    python = directory / "python.json"
    verified = json.loads(original[python])
    tests = [
        ("foreign checkout", {"checkout_sha": "0" * 40}, "INVALID"),
        ("foreign run", {"run_id": str(int(env["GITHUB_RUN_ID"]) + 1)}, "INVALID"),
        ("stale attempt", {"attempt": str(int(env["GITHUB_RUN_ATTEMPT"]) + 1)}, "INVALID"),
        ("wrong case", {"case_id": "DOCS-001"}, "INVALID"),
        ("wrong schema", {"schema_version": True}, "INVALID"),
        ("bad environment", {"environment": {}}, "INVALID"),
        ("wrong evidence hash", {"evidence_sha256": "0" * 64}, "INVALID"),
        ("wrong case plan", {"case_plan_sha256": "0" * 64}, "case_plan_sha256 does not match"),
        ("suite failure", {"status": "fail"}, "| FAIL |"),
        ("skipped suite", {"status": "skip"}, "| SKIP |"),
        ("blocked suite", {"status": "blocked"}, "| BLOCKED |"),
        ("undeclared suite", {"check_id": "extra"}, "undeclared check receipt"),
    ]
    for name, changes, detail in tests:
        write_json(python, {**verified, **changes})
        run(command, project, result=1, includes=detail, env=quiet_env)
        print(f"Rejected {name}.")
    python.unlink()
    uppercase = directory / "python.JSON"
    uppercase.write_bytes(original[python])
    run(command, project, result=1, includes="| python-check | MISSING |", env=quiet_env)
    uppercase.unlink()
    python.write_bytes(original[python])
    duplicate = directory / "copy.json"
    duplicate.write_bytes(original[python])
    run(command, project, result=1, includes="DUPLICATE", env=quiet_env)
    duplicate.unlink()
    python.write_text('{"check_id":"python-check","check_id":"python-check"}', encoding="utf-8")
    run(command, project, result=1, includes="invalid receipt", env=quiet_env)
    python.write_bytes(original[python])
    old_observation = observation.read_bytes()
    observation.write_bytes(old_observation + b" ")
    run(command, project, result=1, includes="INVALID", env=quiet_env)
    observation.write_bytes(old_observation)
    print("Rejected missing and duplicate receipts, duplicate JSON keys, and changed observation bytes.")

    duplicate_observation = b'{"unit_cents":120,"\\u0075nit_cents":125,"quantity":3,"total_cents":375}'
    observation.write_bytes(duplicate_observation)
    run([sys.executable, str(EXAMPLE / "check.py")], project, result=1,
        includes="duplicate JSON key: unit_cents", env=quiet_env)
    failed_receipt = json.loads(python.read_bytes())
    if failed_receipt["status"] != "fail" or failed_receipt["evidence_sha256"] != hashlib.sha256(duplicate_observation).hexdigest():
        raise AssertionError("duplicate observation must retain its original digest and failing status")
    run(command, project, result=1, includes="| python-check | FAIL |", env=quiet_env)
    observation.write_bytes(old_observation)
    python.write_bytes(original[python])
    print("Verified duplicate observation rejection and failing shared evidence receipt.")

    variant = observation.with_name("plan-variant.json")
    plan = json.loads((project / EXAMPLE / "case.json").read_bytes())
    write_json(variant, {**plan, "required_checks": ["python-check"]})
    node = directory / "node.json"
    node.unlink()
    run([*command[:2], "--case", str(variant), "--receipts", str(directory), "--evidence", str(observation)],
        project, result=1, includes="case_plan_sha256 does not match", env=quiet_env)
    node.write_bytes(original[node])

    write_json(variant, {**plan, "shared_evidence": False})
    digest = hashlib.sha256(variant.read_bytes()).hexdigest()
    for path, blob in original.items():
        write_json(path, {**json.loads(blob), "evidence_sha256": None, "case_plan_sha256": digest})
    verify = [*command[:2], "--case", str(variant), "--receipts", str(directory)]
    run(verify, project, includes="Overall: PASS", env=quiet_env)

    write_json(variant, {**plan, "schema_version": 1, "shared_evidence": False})
    run(verify, project, result=1, includes="INVALID", env=quiet_env)
    for path, blob in original.items():
        legacy = json.loads(blob)
        legacy.pop("case_plan_sha256")
        write_json(path, {**legacy, "schema_version": 1, "evidence_sha256": None})
    legacy_output = run(verify, project, includes="Overall: PASS", env=quiet_env)
    if "Legacy receipt v1" not in legacy_output:
        raise AssertionError("legacy proof should disclose the missing plan binding")
    print("Verified exact plan binding, rejection of changed required checks, and matching v1 compatibility.")


def verify_missing_helpers(project, work, command, directory, observation, env):
    quiet_env = {key: value for key, value in env.items() if key != "GITHUB_STEP_SUMMARY"}
    original = {path.name: json.loads(path.read_bytes()) for path in directory.glob("*.json")}
    for helper in ("source_commit.py", "validate_catalog.py"):
        partial = work / helper.removesuffix(".py")
        run(["git", "clone", "--no-hardlinks", str(project), str(partial)], work)
        path = "test-vault/" + helper
        run(["git", "rm", "--cached", "--", path], partial)
        run(["git", "-c", "user.name=Test Vault Fixture", "-c", "user.email=fixture@example.invalid",
             "-c", "commit.gpgsign=false", "commit", "-qm", "Leave one copied helper untracked"], partial)
        checkout = run(["git", "rev-parse", "HEAD"], partial).strip()
        receipts = partial / "receipts"
        receipts.mkdir()
        for name, record in original.items():
            write_json(receipts / name, {**record, "checkout_sha": checkout})
        run([*command[:2], "--case", str(EXAMPLE / "case.json"), "--receipts", str(receipts),
             "--evidence", str(observation)], partial, result=1,
            includes=f"receipt source must be tracked in the intended Git checkout: {Path(path)}",
            env=quiet_env)
        print(f"Rejected untracked receipt helper {helper}.")



def verify_readme_block(project, work, env):
    readme = (project / EXAMPLE / "README.md").read_text(encoding="utf-8")
    block = readme.split("```bash\n", 1)[1].split("```", 1)[0]
    fixtures = (
        ("pass", None, None, "Overall: PASS"),
        ("node-fail", "app.test.mjs", "\ntest('controlled failure', () => assert.fail('regression'));\n",
         "| node-test | FAIL |"),
        ("python-fail", "check.py", None, "| python-check | FAIL |"),
        ("missing", "run-node.mjs", "\nprocess.exit(1);\n", "| node-test | MISSING |"),
    )
    for name, filename, change, expected in fixtures:
        fixture = work / ("example-" + name)
        run(["git", "clone", "--no-hardlinks", str(project), str(fixture)], work)
        if filename:
            path = fixture / EXAMPLE / filename
            text = path.read_text(encoding="utf-8")
            if name == "python-fail":
                text = text.replace("unit_cents, quantity = 125, 3", "unit_cents, quantity = 126, 3")
            elif name == "missing":
                text = change + text
            else:
                text += change
            path.write_text(text, encoding="utf-8")
            run(["git", "add", "."], fixture)
            run(["git", "-c", "user.name=Test Vault Fixture", "-c", "user.email=fixture@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "-qm", name], fixture)
        run(["bash", "-e", "-c", block], fixture, result=0 if name == "pass" else 1, includes=expected,
            env={**env, "GITHUB_STEP_SUMMARY": "", "TMPDIR": str(work)})
        print(f"Verified the copied README command for {name}.")

def verify_sha256_checkout(project, work, command, directory, observation, env):
    target = work / "sha256"
    shutil.copytree(project, target, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    run(["git", "init", "-q", "--object-format=sha256"], target)
    run(["git", "add", "."], target)
    run(["git", "-c", "user.name=Test Vault Fixture", "-c", "user.email=fixture@example.invalid",
         "-c", "commit.gpgsign=false", "commit", "-qm", "SHA-256 fixture"], target)
    checkout = run(["git", "rev-parse", "HEAD"], target)
    receipts = work / "sha256-receipts"
    receipts.mkdir()
    for path in directory.glob("*.json"):
        write_json(receipts / path.name, {**json.loads(path.read_bytes()), "checkout_sha": checkout})
    args = [*command[:4], "--receipts", str(receipts), "--evidence", str(observation)]
    run(args, target, includes="Overall: PASS", env={**env, "GITHUB_STEP_SUMMARY": ""})
    node = receipts / "node.json"
    write_json(node, {**json.loads(node.read_bytes()), "checkout_sha": "0" * 64})
    run(args, target, result=1, includes="checkout_sha does not match", env={**env, "GITHUB_STEP_SUMMARY": ""})


def verify_upgrade(work):
    project = work / "project"
    previous = ROOT / "versions/v0.0.2/starter"
    shutil.copytree(previous, project)
    case_file = project / "test-vault/cases.md"
    old_cases = case_file.read_bytes()
    old_workflow = (project / ACTION).read_bytes()
    run(["git", "init", "-qb", "trunk"], project)
    run([sys.executable, str(VALIDATOR)], project, includes="1 unique cases")
    (project / "existing_test.mjs").write_text(
        "import assert from 'node:assert/strict';\nassert.equal(6 * 7, 42);\n", encoding="utf-8",
    )
    run(["node", "--test", "existing_test.mjs"], project, includes="pass 1")
    for file in ("verify_receipts.py", "source_commit.py", "validate_catalog.py", "evidence.md", "UPGRADE.md"):
        shutil.copy2(STARTER / "test-vault" / file, project / "test-vault" / file)
    shutil.copytree(STARTER / EXAMPLE, project / EXAMPLE)
    case_file.write_bytes(old_cases.rstrip(b"\n") + b"\n" + CASE_ROW.encode())
    if (project / ACTION).read_bytes() != old_workflow:
        raise AssertionError("Opt-in altered the existing workflow")
    run([sys.executable, str(VALIDATOR)], project, includes="2 unique cases")
    run(["node", "--test", "existing_test.mjs"], project, includes="pass 1")
    run(["git", "add", "."], project)
    run(["git", "-c", "user.name=Test Vault Fixture", "-c", "user.email=fixture@example.invalid",
         "-c", "commit.gpgsign=false", "commit", "-qm", "Opt in to receipts"], project)

    directory, observation = work / "receipts", work / "quote.json"
    directory.mkdir()
    env = {
        **os.environ, "GITHUB_RUN_ID": os.environ.get("GITHUB_RUN_ID", "1"),
        "GITHUB_RUN_ATTEMPT": os.environ.get("GITHUB_RUN_ATTEMPT", "1"),
        "VAULT_EXAMPLE_PYTHON": sys.executable,
        "VAULT_EXAMPLE_EVIDENCE": str(observation), "VAULT_EXAMPLE_RECEIPTS": str(directory),
    }
    command = [
        sys.executable, "test-vault/verify_receipts.py", "--case", str(EXAMPLE / "case.json"),
        "--receipts", str(directory), "--evidence", str(observation),
    ]
    suites = [
        ["node", str(EXAMPLE / "run-node.mjs")],
        [sys.executable, str(EXAMPLE / "check.py")],
    ]
    statuses = [subprocess.run(suite, cwd=project, env=env, check=False, timeout=75).returncode for suite in suites]
    print(run(command, project, includes="Overall: PASS", env=env))
    if any(statuses):
        raise AssertionError("Every example suite must also exit successfully")
    hidden = work / "commented-catalog.md"
    hidden.write_bytes(old_cases + b"\n<!--\n" + (HEADER + DIVIDER + CASE_ROW).encode() + b"-->\n")
    run([*command, "--catalog", str(hidden)], project, result=1,
        includes="case ID must be registered", env={**env, "GITHUB_STEP_SUMMARY": ""})
    verify_readme_block(project, work, env)
    verify_missing_helpers(project, work, command, directory, observation, env)
    verify_sha256_checkout(project, work, command, directory, observation, env)
    test_receipts(project, env, command, directory, observation)
    print("Verified v0.0.2 opt-in alongside the existing catalog, workflow, and project test.")


if __name__ == "__main__":
    with TemporaryDirectory() as directory:
        verify_upgrade(Path(directory))
