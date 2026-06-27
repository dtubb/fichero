# Architecture-doc reconciliation (for the archdocs lane)

When `site/docs/` was consolidated into `docs/` (lane/review, 2026-06-27), the
curated *published* architecture overviews differed from the deeper internal
`docs/architecture/` versions. To avoid losing the public prose, the three
differing published files were parked here for the **archdocs lane** to
reconcile into the canonical `docs/architecture/` tree:

| parked file | reconcile into |
|---|---|
| `published-architecture-api-overview.md`     | `docs/architecture/api/overview.md` (or `docs/architecture/fichero-engine/overview.md` after the rename) |
| `published-architecture-swiftui-overview.md` | `docs/architecture/swiftui/overview.md` (or `docs/architecture/fichero/overview.md` after the rename) |
| `published-architecture-release-process.md`  | `docs/architecture/release-process.md` |

`site/docs/architecture/overview.md` was identical to `docs/architecture/overview.md`
and was dropped. The mkdocs nav now points at the `docs/architecture/` versions.
