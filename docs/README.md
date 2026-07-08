# Fichero Documentation

Two guides, for two readers. This page is the landing for anyone browsing
`docs/` on GitHub; the published site's home is [`index.md`](index.md).

- **[User Guide](user/README.md)** — using Fichero. Install, import, read, search,
  run workflows. Start with [What Fichero Is](user/what-fichero-is.md), or check the
  [feature matrix](user/features.md) for what actually ships today.
- **[Contributor Guide](contributor/README.md)** — building Fichero. Architecture,
  the OpenAPI contract, the action registry, the security model, the release lane.

Operational rules for agents live in [`AGENTS.md`](../AGENTS.md); the product north
star in [`CONSTITUTION.md`](../CONSTITUTION.md).

> Every `.md` under this folder is published as a public page — `nav` in
> `mkdocs.yml` controls navigation, not publication. Anything that must not be
> public belongs outside `docs/`. `scripts/check_docs_publication.py` enforces this.
