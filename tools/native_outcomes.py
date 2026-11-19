"""Read the supported native runners' positive test results."""

import json
import re


NATIVE_RUNNERS = {"go-json", "node-tap", "rust-libtest", "unittest"}


def go_events(output):
    return (json.loads(line) for line in output.splitlines() if line.startswith("{"))


def skipped_tests(runner, output):
    if runner == "go-json":
        return sum(bool(event.get("Test") and event.get("Action") == "skip") for event in go_events(output))
    pattern = {
        "node-tap": r"^# skipped (\d+)\s*$",
        "rust-libtest": r"^test result: ok\. .*? (\d+) ignored;",
        "unittest": r"^OK \([^\n]*?skipped=(\d+)",
    }[runner]
    return sum(map(int, re.findall(pattern, output, re.M)))


def passed_tests(runner, output):
    if runner == "go-json":
        return sum(
            bool(event.get("Test") and event.get("Action") == "pass")
            for event in go_events(output) if isinstance(event, dict)
        )
    if runner == "node-tap":
        return int(matches[-1]) if (matches := re.findall(r"^# pass (\d+)\s*$", output, re.M)) else 0
    if runner == "rust-libtest":
        return int(matches[-1]) if (matches := re.findall(
            r"^test result: ok\. (\d+) passed;", output, re.M,
        )) else 0
    if runner == "unittest":
        counts = re.findall(r"^Ran (\d+) tests? in ", output, re.M)
        summaries = re.findall(r"^OK(?: \(([^\n]*)\))?\s*$", output, re.M)
        if counts and summaries:
            unpassed = sum(map(int, re.findall(r"(?:skipped|expected failures)=(\d+)", summaries[-1])))
            return max(0, int(counts[-1]) - unpassed)
    return 0
