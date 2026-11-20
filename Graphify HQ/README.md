# Graphify HQ

Maps for the [archived Test Vault templates](../versions/README.md).

Current archived version is **v0.0.3**.

- [v0.0.3](v0.0.3/README.md)
- [v0.0.2](v0.0.2/README.md)
- [v0.0.1](v0.0.1/README.md)

## Veraphify v0.0.9 adoption

Use [Veraphify v0.0.9 at `ed56500`](https://github.com/vixttha/Veraphify/commit/ed5650085e33cf142a37de695757a4df999a7cf3) to import, verify, and look up source-linked archives. This Git SHA is the merged mechanical revision. The [adopter walkthrough](https://github.com/vixttha/Veraphify/blob/ed5650085e33cf142a37de695757a4df999a7cf3/docs/adopter-walkthrough.md) documents the archive commands and limits. The Graphify producer and the Veraphify archive reader have separate version pins.

The public adoption check archives a pinned Lydite checkout and verifies the inventory implementation citation. Lydite's release and language suites have their own version and evidence.

The [public workflow](../.github/workflows/veraphify-adoption.yml) checks the source pin, runs the Graphify MCP check, compares the archive SHA-256, and verifies the citation against the exact Git blob. The disposable archive version `v0.0.0.1` identifies the probe. Each public run retains a small receipt with the adopter SHA, Veraphify SHA, and citation.
