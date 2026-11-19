"""List and run the checks declared in Lydite language manifests."""

import argparse
import json
import os
import re
import subprocess
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory


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


def run_cases(inventory, languages):
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "DOTNET_CLI_TELEMETRY_OPTOUT": "1"}
    print(f"Checkout {sha} | run {env.get('GITHUB_RUN_ID', 'local')} | attempt {env.get('GITHUB_RUN_ATTEMPT', 'n/a')}", flush=True)
    for slug in languages:
        for case in inventory[slug]["cases"]:
            print(f'{case["id"]} | {case["purpose"]}', flush=True)
            with TemporaryDirectory(prefix="lydite-") as temp:
                for argv in case["commands"]:
                    command = [arg.replace("{tmp}", temp) for arg in argv]
                    subprocess.run(command, cwd=ROOT / "languages" / slug, env=env, check=True, timeout=180)
            print(f'{case["id"]} | PASS', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--run", metavar="LANGUAGE", help="execute one language folder")
    group.add_argument("--runner", choices=sorted(RUNNERS), help="execute every case assigned to the specified runner")
    args = parser.parse_args()
    try:
        inventory = read_inventory(ROOT / "languages")
        if args.run:
            if args.run not in inventory:
                raise ValueError(f"Unknown language folder: {args.run}")
            run_cases(inventory, [args.run])
        elif args.runner:
            languages = [slug for slug, manifest in inventory.items() if manifest["runner"] == args.runner]
            if not languages:
                raise ValueError(f"No language folders were assigned to {args.runner}")
            run_cases(inventory, languages)
        else:
            print_inventory(inventory)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Lydite inventory: {error}\n")


if __name__ == "__main__":
    main()
