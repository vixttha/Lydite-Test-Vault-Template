# Standalone v0.0.4 release candidate

The standalone foundation entered Lydite's main branch at [fe7b00a](https://github.com/vixttha/Lydite-Test-Vault-Template/commit/fe7b00aa17862d7a01dfd15481594be837bc6d9f). The inherited starter and frozen archives are part of the Test Vault lineage described in the [version index](../versions/README.md). The hardening commits v0.0.3.1 through v0.0.3.15 prepare Lydite's standalone v0.0.4 for owner review.

## Draft changelog

- Require positive native test results, retain one outcome per case, and upload synthetic receipts for both passing and nonpassing examples.
- Verify checkout identity, select the declared .NET SDK, validate metadata and normalized test paths, and accept ordinary GitHub Markdown catalog tables.
- Rehearse the full install alongside the catalog-only starter, include the MIT notice, and ignore generated Python bytecode.
- Rebuild the historical Graphify maps from their pinned public sources, link archived v0.0.1 references, and reject malformed input in the shared quote example.
- Generate a release-candidate receipt after the public Ubuntu and Windows checks, install rehearsal, and Graphify verification succeed.

## Evidence for owner review

1. Use the public workflow run for the candidate commit. Download `lydite-release-candidate-attempt-*` from that run and verify its checkout SHA and tree against the proposed commit. A pull request run can record the merge checkout and pull request head separately.
2. Review the linked per-case and complete-install artifacts from the same attempt, before the earliest supporting-artifact expiry recorded in the receipt. All three supporting artifacts and the candidate receipt request 30-day retention. A selective rerun that reuses earlier jobs cannot produce a new receipt. Use **Re-run all jobs** to obtain a complete same-attempt evidence set. Confirm the intended failing fixture, the skipped fixture and the zero-test fixture are correctly rejected and that the independent case after a failure still executed.
3. Confirm the Graphify job rebuilt all three intended archive versions and rejected archive and graph byte drift. Review the issue acceptance criteria and open findings before approving publication.
4. Obtain owner approval before landing or publishing v0.0.4. If the eventual release commit changes, repeat verification for that commit before creating a release tag. Any trial in a separate project is a separate owner decision.
