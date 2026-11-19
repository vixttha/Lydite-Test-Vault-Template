"""Required examples in Lydite's own public validation workflow."""

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
