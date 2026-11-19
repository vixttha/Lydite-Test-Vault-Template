# Using Lydite

## Install the complete Vault

From a Lydite Git checkout, use the [starter install](../starter/test-vault/README.md#install-in-an-existing-repository) to add the catalog and workflow. Also copy `tools/inventory.py`, `tools/native_outcomes.py`, and each desired `languages/<language-folder>/` directory to the same paths in the target repository. Also copy `tools/node_outcomes.mjs` for the JavaScript or TypeScript tracks. Review collisions in an existing project. Use the runtimes listed in the selected manifests. The inventory discovers folders under `languages/` by their `metadata.json` or the combination of `GUIDE.md` and `tests/`. Unrelated folders can remain alongside them.

From the target repository root, run `python3 tools/inventory.py` to check the declarations. Run `python3 tools/inventory.py --run python` for the Python example if installed. Replace the sample with a test of the real project entry point and register that test in the manifest. Add the same command to the target's CI once the runtime is set up. The copied catalog workflow checks the catalog; the language execution command runs the selected tests.

## Pick one behavior

Choose the language or runtime that controls the behavior. A second language can provide independent evidence when it reads the same observation through a different implementation or checks a real client boundary.

1. Write a stable case ID, the project risk or contract, the fixture, and an observable expected result.
2. Start in the matching [language folder](../languages). The guide explains what that runtime is suited to test. The metadata maps the example to its command, runner, and test file.
3. Adapt the runnable example to the actual project entry point. Include a known-bad or boundary input where it supplies distinct evidence. Keep fixtures synthetic and their outputs deterministic.
4. Record the command and result in the [case and run receipt](../starter/test-vault/case-and-receipt.md). When suites share an observation, use the [receipt verifier](../starter/test-vault/evidence.md) to bind results to the same checkout, run, attempt, and observation bytes.

## Get the inventory

Run `python3 tools/inventory.py` from the repository root. Counts come from declared cases and unique primary test paths. Support files, such as a .NET project file, are tracked separately. The inventory checks that a test directory contains the declared files and case IDs are unique. A suite's individual assertion count belongs to the native runner report.

Keep primary and support fixtures inside the language's real `tests/` directory. File symlinks and redirected test roots are rejected.

Keep planned cases in a project test plan. Once an assertion exists, record its code location. Treat a case as verified only after it runs for the intended checkout and environment. Store skipped runs and known failures as their actual outcomes, even when the surrounding job is green.

## Run the examples

Add `--evidence path/to/report.json` to write one record per selected case. For repeatable exact-checkout attribution, use a report directory outside the checkout or an explicitly ignored output directory. For example, on Bash use `report_dir=$(mktemp -d)` and then add `--evidence "$report_dir/report.json"`. Keep generated reports outside tracked files, language and tool inputs, and Git metadata. Each record lists the declared command arguments, declared and observed runtime, and PASS, FAIL, SKIP, or BLOCKED outcome. The ordered `command_results` list maps to the declared command indexes and records process outcomes and exit codes when available. Stages skipped after an earlier failure are recorded as NOT_RUN. A clean Git checkout receives its commit SHA. Modified and extracted checkouts can run locally and report MODIFIED or UNVERSIONED without claiming an exact commit. If the verified checkout changes at a probe or command boundary, the report is marked DRIFTED and loses its claimed checkout SHA. Later cases are blocked. Hosted CI requires a clean checkout and uploads those reports on passing and failing runs, with the checkout, run and attempt, job, and runner image information.

Every manifest case binds its outcome to its primary `test` file. Native runners require `native_test` with the expected native name. Python `unittest` uses a qualified class and method name and verifies the reported method's source file. Node and Go run the declared file explicitly. For Node, use an array such as `["outer suite", "inner suite", "test name"]` as `native_test` when the leaf name is shared across suites. Rust verifies the compiler input and the resulting case-local binary. A suite-wide pass cannot replace a missing named result.

For a standalone assertion, point a supported interpreter directly at the primary file, or build the declared C++ or C# source and immediately run the resulting case-local artifact. C# projects explicitly include the primary source. Set the optional zero-based `assertion_command_index` to identify an assertion stage before post-processing. See the language manifests for supported invocation shapes.

For a case with a `native_runner`, the final command supplies the native verdict by default. Set the optional zero-based `native_command_index` when build, test and post-processing commands appear in the same case and the test command is earlier. Every command must still complete successfully.

Run `python3 tools/inventory.py --run <language-folder>` with the runtime listed in that folder's metadata. The arguments run from the language folder. A `{tmp}` argument is replaced with a fresh temporary directory. Lydite's CI executes the examples on standard public GitHub-hosted Ubuntu and Windows runners and records the exact checkout and result for each case.

The copied [v0.0.3 starter](../starter/test-vault/README.md) remains available for adopters who only need a catalog and optional receipts. The legacy Graphify maps under [Graphify HQ](../Graphify%20HQ/README.md) describe the archived template versions. The [archive manifest](../versions/manifest.json) pins the source. On Ubuntu with Python 3.12, install the locked Graphify and Markdown requirements from `tools/graphify/requirements.txt` and `tools/markdown-requirements.txt` and run `PYTHONHASHSEED=0 python tools/graphify/version_maps.py "$(mktemp -d)" --fetch-upstream --check` to fetch the three public source commits and compare freshly rebuilt maps with the committed snapshots.

## Validation and release receipts

- **Routine validation.** Pushes to [the workflow's allowed branches](../.github/workflows/validate.yml#L5), pull requests, and manual runs with an empty version publish `lydite-validation-attempt-*` when all supporting checks succeed. The allowed push branches are `main` and the historical `hardening/v0.0.3` branch. Open or update a PR, or dispatch with an empty version, to validate another branch.
- **Named release candidate.** Manually run **Lydite validation** on the intended ref with a `vMAJOR.MINOR.PATCH` target. Preflight records an available or rejected verdict and the reason in a separate artifact. A published version, conflicting tag, invalid target or unavailable authoritative result blocks candidate evidence. The workflow checks release state again immediately before issuing a receipt.
- **Evidence.** Successful aggregate receipts bind the checkout, tree and run attempt to downloaded and verified Linux, Windows, adoption and Graphify payloads. Early language failures retain a blocked lane record where the runner can publish it.

Follow the [owner release review](release-review.md) for a publication decision. Read `receipt.json` in the relevant artifact and match its checkout and tree to the review target. Routine runs supersede older routine runs on the same ref. A named run is grouped by ref and version, so repeating that pair supersedes the earlier run for that pair.

## Check maintained documentation

Install the pinned parser with `python3 -m pip install --require-hashes -r tools/markdown-requirements.txt`. Run `python3 tools/check_doc_links.py` from the project checkout.

Use `python3 tools/check_doc_links.py --tree HEAD` to verify the committed snapshot. The default command checks the working tree, including draft files.

## Branchwell adoption evidence

The [Branchwell plan](https://github.com/vixttha/Lydite-Test-Vault-Template/blob/46b63f7e0db3b56ed80cf3bbd76ce7511f25fa53/docs/branchwell-adoption.md) lists proposed adopter cases. The Branchwell workflow validates the plan and Lydite's declaration inventory. Record execution under the actual Branchwell checkout with case results and the manual status for UI-002.
