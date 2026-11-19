# Provenistem for Lydite

Lydite's host-local Ideas and Features library uses the portable Provenistem v0.0.2 record format. Use the [Ideas index](ideas/INDEX.md) for possibilities and their source issues and the [Features index](features/INDEX.md) for capabilities and scoped verification.

The initial records distinguish the main-branch starter, verified draft work and proposed fixes. Evidence for a draft applies to its cited commit. Release membership remains `NOT_ASSERTED`. GitHub issues, pull requests and release records remain the engineering sources.

## Maintain records

1. Copy the [idea example](templates/idea.example.json) or [feature example](templates/feature.example.json) into the corresponding `records/` directory. Replace the sample details and assign the next unused ID.
2. Link related ideas from feature records. Cite public Lydite evidence with its exact commit and scope. Record implementation and testing independently.
3. Regenerate the two indexes and check the populated library from the repository root.

```sh
python provenistem/tools/library.py build
python provenistem/tools/library.py check
```

The JSON records remain authoritative if an index gets stale. Validation checks record structure, links between records and index freshness. The portable schemas, examples and validator retain the [upstream MIT notice](LICENSE).
