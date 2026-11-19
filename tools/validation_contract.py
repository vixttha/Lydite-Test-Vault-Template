"""Required examples in Lydite's own public validation workflow."""

import argparse
import json
import os
from pathlib import Path

REQUIRED_LANES = {
    "ubuntu-24.04": {
        "bash": ["BASH-001"], "cpp": ["CPP-001"], "csharp": ["CSHARP-001"],
        "fsharp": ["FSHARP-001"], "go": ["GO-001"], "haskell": ["HASKELL-001"],
        "java": ["JAVA-001"], "javascript": ["JAVASCRIPT-001"], "lua": ["LUA-001"],
        "python": ["PYTHON-001"], "ruby": ["RUBY-001"], "rust": ["RUST-001"],
        "typescript": ["TYPESCRIPT-001"],
    },
    "windows-latest": {"powershell": ["POWERSHELL-001"]},
}


ADOPTION_OUTCOMES = {
    "adoption-pass.json": {"PYTHON-001": "PASS"},
    "adoption-fail.json": {"PYTHON-001": "FAIL", "PYTHON-002": "BLOCKED", "PYTHON-003": "PASS"},
    "adoption-skip.json": {"PYTHON-001": "SKIP"},
    "adoption-empty.json": {"PYTHON-001": "FAIL"},
}


def validate_inventory(inventory):
    observed = {runner: {} for runner in REQUIRED_LANES}
    for language, data in inventory.items():
        observed[data["runner"]][language] = sorted(case["id"] for case in data["cases"])
    differences = [
        f"{runner}/{language}"
        for runner, expected in REQUIRED_LANES.items()
        for language in sorted(expected.keys() | observed[runner].keys())
        if expected.get(language) != observed[runner].get(language)
    ]
    if differences:
        raise ValueError(f"upstream language inventory differs at {', '.join(differences)}")


def lane_failure(runner, stage, env):
    return {
        "schema_version": 1,
        "kind": "pre-execution-failure",
        "outcome": "BLOCKED",
        "failed_stage": stage,
        "expected_checkout_sha": env.get("GITHUB_SHA"),
        "run_id": env.get("GITHUB_RUN_ID"),
        "attempt": env.get("GITHUB_RUN_ATTEMPT"),
        "runner": runner,
        "cases": [{"case_id": case, "outcome": "NOT_RUN"}
                  for cases in REQUIRED_LANES[runner].values() for case in cases],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("runner", choices=REQUIRED_LANES)
    parser.add_argument("stage", choices=["setup", "inventory"])
    args = parser.parse_args()
    args.path.parent.mkdir(parents=True, exist_ok=True)
    args.path.write_text(json.dumps(lane_failure(args.runner, args.stage, os.environ), indent=2) + "\n",
                         encoding="utf-8")
