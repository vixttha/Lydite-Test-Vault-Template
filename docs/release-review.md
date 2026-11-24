# Review a Lydite release candidate

[Published v0.0.4 history](release-candidate.md) is the record for the released version. [Checkpoint issue #35](https://github.com/vixttha/Lydite-Test-Vault-Template/issues/35) tracks hardening for the next candidate.

## Candidate changes under review

- Tighten native verdicts and bind shared receipts to whole-suite outcomes.
- Preserve portable copy-in installation, receipt and checkout identity, and report output safety.
- Validate visible catalog cases and reader navigation in maintained and copied README files.
- Verify exact archive pins, lockfiles, maps, and Graphify readback.
- Validate downloaded same-attempt supporting artifacts before issuing a combined receipt.

## Owner decision

A named receipt identifies a target and tested checkout with publication state awaiting owner approval. The validation workflow uses read-only permissions and can generate evidence for review. The repository owner decides whether to merge or publish.

Record the following in the hardening PR or release review before publishing:

| Field | Current decision |
|---|---|
| Intended release tag | Pending owner selection |
| Exact commit and tree selected for publication | Pending owner selection |
| Successful named candidate receipt, run and attempt for that commit | Pending candidate evidence |
| Owner approval reference for that tag and SHA | Pending approval |

If merging changes the commit selected for publication, verify the actual proposed release commit and use its evidence for the release decision. After approval, confirm the remote tag target and published release record agree with that decision.

Review effective branch and tag controls in GitHub when setting up this release. The hardening review observed no active rulesets and an unprotected main branch. The owner's decision is the current release gate. Record any later settings decision and verify the effective rules separately. Keep publication and settings changes under the owner's control.
