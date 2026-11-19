"""Validate the downloaded payloads that back a public Lydite receipt."""

import hashlib
import io
import json
import re
import subprocess
import zipfile

from validation_contract import ADOPTION_OUTCOMES, REQUIRED_LANES


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def read_documents(data, digest):
    if digest != f"sha256:{sha256(data)}":
        raise ValueError("downloaded ZIP digest differs from GitHub metadata")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) != len({entry.filename for entry in entries}):
            raise ValueError("downloaded ZIP contains duplicate paths")
        return {entry.filename: json.loads(archive.read(entry)) for entry in entries if not entry.is_dir()}


def require_fields(document, expected):
    if not isinstance(document, dict) or any(document.get(key) != value for key, value in expected.items()):
        fields = ", ".join(expected)
        raise ValueError(f"report fields differ from the required values ({fields})")


def verify_cases(report, expected, scope, runner=None):
    require_fields(report, {"schema_version": 1, "run_id": scope["run_id"], "attempt": scope["attempt"]})
    checkout = report.get("checkout_sha")
    if not isinstance(checkout, str) or not re.fullmatch(r"[0-9a-f]{40}", checkout):
        raise ValueError("case report lacks an exact checkout SHA")
    require_fields(report.get("source"), {"state": "CLEAN", "commit": checkout, "base_commit": checkout})
    if runner:
        require_fields(report, {"runner": runner, "checkout_sha": scope["checkout_sha"]})
    rows = report.get("cases")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("case report lacks structured cases")
    observed = {row["case_id"]: row["outcome"] for row in rows}
    if len(observed) != len(rows) or observed != expected:
        raise ValueError("case report has missing, duplicate, unexpected, or non-passing cases")
    if runner:
        languages = {case: language for language, cases in REQUIRED_LANES[runner].items() for case in cases}
        if any(row.get("language") != languages[row["case_id"]] or row.get("declared_runner") != runner
               for row in rows):
            raise ValueError("case report has an unexpected track or runner assignment")


def verify_payload(documents, prefix, scope, graphify):
    if prefix == "lydite-adoption":
        if set(documents) != set(ADOPTION_OUTCOMES) | {"adoption-index.json"}:
            raise ValueError("adoption artifact files differ from the required reports")
        require_fields(documents["adoption-index.json"], {**scope, "kind": "adoption-verification"})
        for name, expected in ADOPTION_OUTCOMES.items():
            verify_cases(documents[name], expected, scope)
    elif prefix == "lydite-graphify":
        if set(documents) != {"validation.json"}:
            raise ValueError("Graphify artifact must contain one validation record")
        require_fields(documents["validation.json"], {**scope, **graphify})
    else:
        runner = prefix.removeprefix("lydite-cases-")
        if runner not in REQUIRED_LANES or set(documents) != {"examples.json"}:
            raise ValueError("language artifact does not contain the required report")
        expected = {case: "PASS" for cases in REQUIRED_LANES[runner].values() for case in cases}
        verify_cases(documents["examples.json"], expected, scope, runner)


def verify_support_payloads(repository, evidence, scope, graphify):
    for item in evidence:
        artifact = item["artifact"]
        name = artifact["name"]
        prefix = name.removesuffix(f"-attempt-{scope['attempt']}")
        try:
            endpoint = f"repos/{repository}/actions/artifacts/{artifact['id']}/zip"
            data = subprocess.check_output(["gh", "api", endpoint])
            documents = read_documents(data, artifact["digest"])
            verify_payload(documents, prefix, scope, graphify)
        except (ValueError, OSError, zipfile.BadZipFile, subprocess.CalledProcessError, KeyError, TypeError) as error:
            raise ValueError(f"could not verify {name}: {error}") from error
