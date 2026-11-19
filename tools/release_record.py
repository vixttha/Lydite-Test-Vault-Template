"""Record the checkout and evidence after the public validation matrix completes."""

import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]


SUPPORTING_JOBS = (
    ("Inventory and starter adoption", "lydite-adoption"),
    ("Language examples (ubuntu-24.04)", "lydite-cases-ubuntu-24.04"),
    ("Language examples (windows-latest)", "lydite-cases-windows-latest"),
    ("Rebuild and verify archived Graphify maps", None),
)


def supporting_evidence(jobs, artifacts, run_id, attempt, run_url):
    entries = []
    for job_name, artifact_prefix in SUPPORTING_JOBS:
        matches = [job for job in jobs if job["name"] == job_name]
        if len(matches) != 1 or any(
            job.get("run_attempt") != attempt or str(job.get("run_id")) != str(run_id)
            or job.get("conclusion") != "success" for job in matches
        ):
            raise ValueError(f"{job_name} has no unique successful job in attempt {attempt}. Re-run all jobs.")
        job = matches[0]
        entry = {"job": job_name, "job_id": job["id"], "attempt": attempt,
                 "job_url": f"{run_url}/job/{job['id']}"}
        if artifact_prefix is not None:
            name = f"{artifact_prefix}-attempt-{attempt}"
            found = [item for item in artifacts if item["name"] == name and not item["expired"]]
            if len(found) != 1 or not found[0].get("expires_at") or not found[0].get("digest"):
                raise ValueError(f"{name} is unavailable or incomplete. Re-run all jobs.")
            item = found[0]
            entry["artifact"] = {
                "name": name, "id": item["id"], "digest": item["digest"], "expires_at": item["expires_at"],
                "url": f"{run_url}/artifacts/{item['id']}",
            }
        entries.append(entry)
    return entries


def github_items(endpoint, key):
    data = subprocess.check_output(["gh", "api", endpoint], text=True)
    return json.loads(data)[key]


def fetch_support(repository, run_id, attempt, run_url):
    prefix = f"repos/{repository}/actions/runs/{run_id}"
    for retry in range(3):
        jobs = github_items(f"{prefix}/attempts/{attempt}/jobs?per_page=100", "jobs")
        artifacts = github_items(f"{prefix}/artifacts?per_page=100", "artifacts")
        try:
            return supporting_evidence(jobs, artifacts, run_id, attempt, run_url)
        except ValueError:
            if retry == 2:
                raise
            time.sleep(2)


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()


def receipt_context(event, version="", pr_head=None, pr_base=None):
    if not event:
        raise ValueError("workflow event is required")
    context = {
        "kind": "validation",
        "event": event,
        "pull_request_head": pr_head or None,
        "pull_request_base": pr_base or None,
    }
    if version:
        if event != "workflow_dispatch":
            raise ValueError("a named release candidate requires an explicit workflow dispatch")
        part = r"(?:0|[1-9][0-9]*)"
        if not re.fullmatch(rf"v{part}\.{part}\.{part}", version):
            raise ValueError("release version must use vMAJOR.MINOR.PATCH")
        context.update(kind="release_candidate", target=version, publication_state="awaiting-owner-approval")
    return context


def github_resource(endpoint, *, allow_missing=False):
    """Read one authoritative GitHub object, treating only an expected 404 as absent."""
    request = Request(f"{os.environ['GITHUB_API_URL'].rstrip('/')}/{endpoint}",
                      headers={"Accept": "application/vnd.github+json"})
    if token := os.environ.get("GH_TOKEN"):
        request.add_unredirected_header("Authorization", f"Bearer {token}")
    try:
        with urlopen(request, timeout=10) as response:
            value = json.load(response)
    except HTTPError as error:
        if allow_missing and error.code == 404:
            return None
        raise ValueError(f"GitHub could not verify {endpoint} (HTTP {error.code})") from error
    except (OSError, ValueError) as error:
        raise ValueError(f"GitHub could not verify {endpoint}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"GitHub returned an invalid object for {endpoint}")
    return value


def verify_candidate_target(repository, version, checkout):
    prefix = f"repos/{repository}"
    release = github_resource(f"{prefix}/releases/tags/{version}", allow_missing=True)
    if release is not None and (release.get("tag_name") != version or release.get("draft") is not True):
        raise ValueError(f"{version} is already published or its release state could not be verified.")
    ref = github_resource(f"{prefix}/git/ref/tags/{version}", allow_missing=True)
    if ref is None:
        # Confirm the repository and checkout are visible before relying on missing-object responses.
        commit = github_resource(f"{prefix}/git/commits/{checkout}")
        if commit.get("sha") != checkout:
            raise ValueError("GitHub returned the wrong object for the validated checkout.")
        return
    if ref.get("ref") != f"refs/tags/{version}":
        raise ValueError(f"GitHub returned the wrong ref for {version}.")
    target = ref.get("object")
    seen = set()
    while isinstance(target, dict):
        sha = target.get("sha")
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha) or sha in seen:
            break
        if target.get("type") == "commit":
            if sha != checkout:
                raise ValueError(f"Tag {version} points to {sha}, not the validated checkout {checkout}.")
            return
        if target.get("type") != "tag":
            break
        seen.add(sha)
        target = github_resource(f"{prefix}/git/tags/{sha}").get("object")
    raise ValueError(f"Could not resolve tag {version} to a Git commit.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--check-target", action="store_true", help="check a named target before running tests")
    args = parser.parse_args()
    if args.check_target == (args.output is not None):
        parser.error("supply an output path or --check-target")
    try:
        context = receipt_context(
            os.environ.get("GITHUB_EVENT_NAME"), os.environ.get("LYDITE_RELEASE_VERSION", ""),
            os.environ.get("CANDIDATE_PR_HEAD"), os.environ.get("CANDIDATE_PR_BASE"),
        )
    except ValueError as error:
        parser.error(str(error))
    checkout = git("rev-parse", "HEAD")
    if checkout != os.environ["GITHUB_SHA"]:
        raise SystemExit("validation checkout differs from the workflow revision")
    repository = os.environ["GITHUB_REPOSITORY"]
    version = context.get("target")
    if args.check_target:
        if version is None:
            parser.error("--check-target requires a named release candidate")
        try:
            verify_candidate_target(repository, version, checkout)
        except ValueError as error:
            raise SystemExit(f"Release candidate rejected: {error}") from error
        print(f"Release target {version} is available for checkout {checkout}.")
        return
    manifest = json.loads((ROOT / "versions/manifest.json").read_text(encoding="utf-8"))
    run_id = os.environ["GITHUB_RUN_ID"]
    run_url = f"{os.environ['GITHUB_SERVER_URL']}/{repository}/actions/runs/{run_id}"
    attempt = int(os.environ["GITHUB_RUN_ATTEMPT"])
    try:
        evidence = fetch_support(repository, run_id, attempt, run_url)
    except (ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"Validation evidence unavailable: {error}") from error
    if version is not None:
        try:
            verify_candidate_target(repository, version, checkout)
        except ValueError as error:
            raise SystemExit(f"Release candidate rejected: {error}") from error
    record = {
        "schema_version": 1,
        **context,
        "checkout_sha": checkout,
        "tree_sha": git("rev-parse", "HEAD^{tree}"),
        "archive_current": manifest["current"],
        "archive_sources": manifest["versions"],
        "run_id": run_id,
        "attempt": str(attempt),
        "run_url": run_url,
        "completed_jobs": ["inventory-and-adoption", "examples (Ubuntu and Windows)", "graphify"],
        "supporting_evidence": evidence,
        "supporting_artifacts_expire_at": min(
            item["artifact"]["expires_at"] for item in evidence if "artifact" in item
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    scope = f"Release candidate {context['target']}" if "target" in context else "Validation receipt"
    print(f"{scope} written for {checkout}.")


if __name__ == "__main__":
    main()
