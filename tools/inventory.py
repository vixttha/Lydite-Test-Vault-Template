"""List and run the checks declared in Lydite language manifests."""

import argparse
import json
import os
import platform
import re
import subprocess
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from native_outcomes import NATIVE_RUNNERS, passed_tests, skipped_tests


ROOT = Path(__file__).resolve().parents[1]
CASE_ID = re.compile(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-[0-9]{3,}")
RUNNERS = {"ubuntu-24.04", "windows-latest"}


def check_files(folder, cases):
    declared = set()
    for case in cases:
        for name in [case["test"], *case["support"]]:
            path = PurePosixPath(name)
            if len(path.parts) < 2 or path.parts[0] != "tests" or ".." in path.parts:
                raise ValueError(f"{folder.name}: expected a path within tests/: {name}")
            declared.add(path.as_posix())

    actual = {
        path.relative_to(folder).as_posix()
        for path in (folder / "tests").rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    if actual != declared:
        raise ValueError(f"{folder.name}: missing {sorted(declared - actual)}, unlisted {sorted(actual - declared)}")


def read_inventory(directory):
    inventory = {}
    seen = set()
    for folder in sorted(directory.iterdir()):
        if not folder.is_dir():
            continue
        manifest = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
        if manifest["schema_version"] != 1 or manifest["runner"] not in RUNNERS:
            raise ValueError(f"{folder.name}: unknown schema or runner")
        if not (folder / "GUIDE.md").is_file():
            raise ValueError(f"{folder.name}: GUIDE.md is missing")
        if any(not isinstance(manifest[k], str) or not manifest[k].strip() for k in ("language", "runtime")):
            raise ValueError(f"{folder.name}: missing language or runtime")

        cases = manifest["cases"]
        if not isinstance(cases, list) or not cases:
            raise ValueError(f"{folder.name}: expected at least one declared case")
        for case in cases:
            case_id = case["id"]
            if not CASE_ID.fullmatch(case_id) or case_id in seen:
                raise ValueError(f"{folder.name}: invalid or duplicate case {case_id}")
            if not case["purpose"].strip() or not isinstance(case["support"], list):
                raise ValueError(f"{case_id}: expected a purpose and a support-file list")
            commands = case["commands"]
            if not isinstance(commands, list) or not commands or any(
                not isinstance(argv, list) or not argv or not all(isinstance(arg, str) and arg for arg in argv)
                for argv in commands
            ):
                raise ValueError(f"{case_id}: expected one or more nonempty argument lists")
            native = case.get("native_runner")
            if native is not None and (not isinstance(native, str) or native not in NATIVE_RUNNERS):
                raise ValueError(f"{case_id}: unknown native runner {native!r}")
            seen.add(case_id)
        check_files(folder, cases)
        inventory[folder.name] = manifest

    if not inventory:
        raise ValueError("No languages found")
    return inventory


def print_inventory(inventory):
    print("| Language | Runtime | Declared cases | Test files | Runner |")
    print("| --- | --- | ---: | ---: | --- |")
    for manifest in inventory.values():
        cases = manifest["cases"]
        test_files = len({case["test"] for case in cases})
        print(f'| {manifest["language"]} | {manifest["runtime"]} | {len(cases)} | {test_files} | {manifest["runner"]} |')
    print(f'\n{sum(len(m["cases"]) for m in inventory.values())} declared cases in {len(inventory)} language folders.')


def execute_case(case, folder, env, *, timeout=180):
    output = ""
    with TemporaryDirectory(prefix="lydite-") as temp:
        for argv in case["commands"]:
            command = [arg.replace("{tmp}", temp) for arg in argv]
            try:
                result = subprocess.run(
                    command, cwd=folder, env=env, check=False, timeout=timeout,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace",
                )
            except subprocess.TimeoutExpired as error:
                if error.stdout:
                    print(error.stdout.decode(errors="replace"), end="", flush=True)
                return "FAIL", f"{argv[0]} timed out after {timeout:g}s"
            except FileNotFoundError:
                return "BLOCKED", f"required executable unavailable: {argv[0]}"
            except OSError as error:
                return "BLOCKED", f"cannot start {argv[0]}: {error}"
            output = result.stdout
            print(output, end="", flush=True)
            if result.returncode:
                return "FAIL", f"{argv[0]} exited with code {result.returncode}"
    if native := case.get("native_runner"):
        try:
            if not passed_tests(native, output):
                if skipped_tests(native, output):
                    return "SKIP", f"{native} reported skipped tests and no passes"
                return "FAIL", f"{native} reported no passing tests"
        except (ValueError, AttributeError):
            return "FAIL", f"{native} reported an invalid result"
    return "PASS", "case passed"


def runtime_version(probe, folder, env):
    if not probe:
        return None
    try:
        result = subprocess.run(
            probe, cwd=folder, env=env, timeout=20, capture_output=True,
            text=True, errors="replace", check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return (result.stdout or result.stderr).splitlines()[0] if result.stdout or result.stderr else None


def checkout_identity(root):
    def git(*args):
        return subprocess.check_output(
            ["git", "-C", str(root), *args], text=True, stderr=subprocess.DEVNULL,
        ).strip()

    try:
        if Path(git("rev-parse", "--show-toplevel")).resolve() != root.resolve():
            return {"state": "UNVERSIONED", "commit": None, "base_commit": None}
        base = git("rev-parse", "HEAD")
        dirty = git("status", "--porcelain=v1", "--untracked-files=all", "--", ".")
    except (OSError, subprocess.CalledProcessError):
        return {"state": "UNVERSIONED", "commit": None, "base_commit": None}
    return {"state": "MODIFIED" if dirty else "CLEAN", "commit": None if dirty else base, "base_commit": base}


def run_cases(inventory, languages, evidence=None):
    source = checkout_identity(ROOT)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "DOTNET_CLI_TELEMETRY_OPTOUT": "1"}
    report = {
        "schema_version": 1,
        "checkout_sha": source["commit"],
        "source": source,
        "run_id": env.get("GITHUB_RUN_ID"),
        "attempt": env.get("GITHUB_RUN_ATTEMPT"),
        "job": env.get("GITHUB_JOB"),
        "runner": env.get("LYDITE_RUNNER"),
        "environment": {
            "os": platform.system(), "release": platform.release(), "architecture": platform.machine(),
            "image_os": env.get("ImageOS"), "image_version": env.get("ImageVersion"),
        },
        "cases": [],
    }
    print(f"Checkout {source['commit'] or source['state']} | run {report['run_id'] or 'local'}"
          f" | attempt {report['attempt'] or 'n/a'}", flush=True)
    for slug in languages:
        manifest = inventory[slug]
        folder = ROOT / "languages" / slug
        runtime = runtime_version(manifest.get("runtime_probe"), folder, env)
        for case in manifest["cases"]:
            print(f'{case["id"]} | {case["purpose"]}', flush=True)
            if env.get("GITHUB_ACTIONS") == "true" and source["state"] != "CLEAN":
                status, reason = "BLOCKED", "hosted evidence requires a clean Git checkout at the Vault root"
            elif manifest.get("runtime_probe") and runtime is None:
                status, reason = "BLOCKED", "declared runtime version probe failed"
            else:
                status, reason = execute_case(case, folder, env)
            print(f'{case["id"]} | {status} | {reason}', flush=True)
            report["cases"].append({
                "case_id": case["id"], "language": slug, "test": case["test"],
                "declared_runner": manifest["runner"], "declared_runtime": manifest["runtime"],
                "observed_runtime": runtime, "commands": case["commands"],
                "outcome": status, "detail": reason,
            })
    if evidence is not None:
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if all(case["outcome"] == "PASS" for case in report["cases"]) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--run", metavar="LANGUAGE", help="execute one language folder")
    group.add_argument("--runner", choices=sorted(RUNNERS), help="execute every case assigned to the specified runner")
    parser.add_argument("--evidence", type=Path, help="write a JSON report for a case run")
    args = parser.parse_args()
    if args.evidence and not (args.run or args.runner):
        parser.error("--evidence requires --run or --runner")
    try:
        inventory = read_inventory(ROOT / "languages")
        if args.run:
            if args.run not in inventory:
                raise ValueError(f"Unknown language folder: {args.run}")
            return run_cases(inventory, [args.run], args.evidence)
        elif args.runner:
            languages = [slug for slug, manifest in inventory.items() if manifest["runner"] == args.runner]
            if not languages:
                raise ValueError(f"No language folders were assigned to {args.runner}")
            return run_cases(inventory, languages, args.evidence)
        else:
            print_inventory(inventory)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Lydite inventory: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
