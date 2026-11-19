"""Record release candidate identity after the public validation matrix completes."""

import argparse
import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    checkout = git("rev-parse", "HEAD")
    if checkout != os.environ["GITHUB_SHA"]:
        raise SystemExit("release candidate checkout differs from the workflow revision")
    manifest = json.loads((ROOT / "versions/manifest.json").read_text(encoding="utf-8"))
    record = {
        "schema_version": 1,
        "target": "v0.0.4",
        "publication_state": "awaiting-owner-approval",
        "checkout_sha": checkout,
        "tree_sha": git("rev-parse", "HEAD^{tree}"),
        "pull_request_head": os.environ.get("CANDIDATE_PR_HEAD") or None,
        "archive_current": manifest["current"],
        "archive_sources": manifest["versions"],
        "run_id": os.environ["GITHUB_RUN_ID"],
        "attempt": os.environ["GITHUB_RUN_ATTEMPT"],
        "run_url": f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}",
        "completed_jobs": ["inventory-and-adoption", "examples (Ubuntu and Windows)", "graphify"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"Draft v0.0.4 release record written for {checkout}.")


if __name__ == "__main__":
    main()
