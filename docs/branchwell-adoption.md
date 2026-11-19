# Branchwell adoption plan

The public workflow checks this plan file and Lydite’s declaration inventory. A passing run records the Lydite checkout. Branchwell case execution requires its own run in the consumer checkout and evidence for each observed case, including the manual status for UI-002.

Base audit: main at 87d25d8. The template already supplies inventory validation, documented installation, and separate execution receipts. The default-branch workflow uses standard hosted Linux and Windows runners. A release-target dispatch on the newer hardening branch failed at its named release target gate, so that run provides no language or archive result.

## Cases

| Case | Priority | Layer | Scenario | Expected result |
| --- | --- | --- | --- | --- |
| DATA-001 | P0 | unit | Compare adjacent 28-day UTC periods around midnight. | Today is excluded and each historical boundary belongs to one period. |
| DATA-002 | P0 | integration | Refresh a repository with a new name and the same GitHub ID. | Work notes and focus survive for the same account. |
| DATA-003 | P0 | integration | View the same repository under a different GitHub account. | The other account does not inherit local work annotations. |
| UI-001 | P1 | unit | Combine topic search, private visibility, work status, and priority. | Only matching repositories appear in stable priority order. |
| UI-002 | P1 | manual | Find a demo repository, save a next action, and reload Work mode. | The action is still visible and opens the same profile. |

Run `npm test` in the Branchwell checkout for the automated cases. Execute UI-002 in the browser against fictional data. Log build commit, observed result and test scope separately from the case catalog. Avoid storing personal repository data in public evidence.
