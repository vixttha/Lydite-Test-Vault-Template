# Provenistem for Lydite

Lydite's host-local Ideas and Features library uses the portable Provenistem v0.0.2 record format. Use the [Ideas index](ideas/INDEX.md) for possibilities and their source issues and the [Features index](features/INDEX.md) for capabilities and scoped verification.

The [November 20 branch audit](BRANCH-AUDIT-2026-11-20.md) maps every observed Lydite branch to its commit, review state, and verification evidence.

The initial six Ideas were adopted and all seven Features were verified for [Lydite v0.0.4](https://github.com/vixttha/Lydite-Test-Vault-Template/releases/tag/v0.0.4). The tag points to `87d25d80d3154d295052412b64b29a0f0f152c27`. The [public run](https://github.com/vixttha/Lydite-Test-Vault-Template/actions/runs/44506598515) and [candidate receipt](https://github.com/vixttha/Lydite-Test-Vault-Template/actions/runs/44506598515/artifacts/14519447654) identify that checkout. The changelog Idea records the publication decision and links the release. Feature test claims cite the jobs that exercised each capability.

The portable schema keeps `release_membership` at `NOT_ASSERTED`. Use the tagged release, linked source and runner evidence to establish what shipped. Use the lifecycle and implementation fields to distinguish a proposal from work that has been adopted or implemented.

## Maintain records

1. Copy the [idea example](templates/idea.example.json) or [feature example](templates/feature.example.json) into the corresponding `records/` directory. Replace the sample details and assign the next unused ID.
2. Link related ideas from feature records. Cite public Lydite evidence with its exact commit and scope. Record implementation and testing independently.
3. Regenerate the two indexes and check the populated library from the repository root.

```sh
python provenistem/tools/library.py build
python provenistem/tools/library.py check
```

The JSON records remain authoritative if an index gets stale. Validation checks record structure, links between records and index freshness. The portable schemas, examples and validator retain the [upstream MIT notice](LICENSE).
