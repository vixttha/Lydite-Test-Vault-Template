# Using Lydite

## Pick one behavior

Choose the language or runtime that controls the behavior. A second language can provide independent evidence when it reads the same observation through a different implementation or checks a real client boundary.

1. Write a stable case ID, the project risk or contract, the fixture, and an observable expected result.
2. Start in the matching [language folder](../languages). The guide explains what that runtime is suited to test. The metadata maps the example to its command, runner, and test file.
3. Adapt the runnable example to the actual project entry point. Include a known-bad or boundary input where it supplies distinct evidence. Keep fixtures synthetic and their outputs deterministic.
4. Record the command and result in the [case and run receipt](../starter/test-vault/case-and-receipt.md). When suites share an observation, use the [receipt verifier](../starter/test-vault/evidence.md) to bind results to the same checkout, run, attempt, and observation bytes.

## Get the inventory

Run `python tools/inventory.py` from the repository root. Counts come from declared cases and unique primary test paths. Support files, such as a .NET project file, are tracked separately. The inventory checks that a test directory contains the declared files and case IDs are unique. A suite's individual assertion count belongs to the native runner report.

Keep planned cases in a project test plan. Once an assertion exists, record its code location. Treat a case as verified only after it runs for the intended checkout and environment. Store skipped runs and known failures as their actual outcomes, even when the surrounding job is green.

## Run the examples

Add `--evidence path/to/report.json` to write one record per selected case. Each record lists its command arguments, declared and observed runtime, and PASS, FAIL, SKIP, or BLOCKED outcome. A clean Git checkout receives its commit SHA. Modified and extracted checkouts can run locally and report MODIFIED or UNVERSIONED without claiming an exact commit. Hosted CI requires a clean checkout and uploads those reports on passing and failing runs, with the checkout, run and attempt, job, and runner image information.

Run `python tools/inventory.py --run <language-folder>` with the runtime listed in that folder's metadata. The arguments run from the language folder. A `{tmp}` argument is replaced with a fresh temporary directory. Lydite's CI executes the examples on standard public GitHub-hosted Ubuntu and Windows runners and records the exact checkout and result for each case.

The copied [v0.0.3 starter](../starter/test-vault/README.md) remains available for adopters who only need a catalog and optional receipts. The legacy Graphify maps under [Graphify HQ](../Graphify%20HQ/README.md) describe the archived template versions. The original version-map builder needs the commit objects named in [the archive manifest](../versions/manifest.json) from the linked source repository if you rebuild those historical snapshots.
