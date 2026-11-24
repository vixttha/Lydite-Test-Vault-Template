"""Read the pinned archive manifest with strict JSON keys."""

import json


def unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate archive manifest field {key!r}")
        result[key] = value
    return result


def load_manifest(text):
    manifest = json.loads(text, object_pairs_hook=unique_fields)
    if not isinstance(manifest, dict):
        raise ValueError("archive manifest must be a JSON object")
    if type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
        raise ValueError("archive manifest schema_version must be integer 1")
    return manifest
