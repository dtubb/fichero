## 2026-06-28

- Added a grounded `Fold status` section to `docs/contributor/node-model.md`
  covering the shipped EPIC #2591 folds, the infra surfaces intentionally not
  folded, and the remaining in-progress/pending items.
- Verified each status claim against merged backend code in
  `fichero-engine/src/fichero/db.py`,
  `fichero-engine/src/fichero/node_prototypes.py`,
  `fichero-engine/src/fichero/node_aliases.py`,
  `fichero-engine/src/fichero/api/routes/bookmarks.py`,
  `fichero-engine/src/fichero/api/routes/mind_palace.py`,
  `fichero-engine/src/fichero/execution/runner.py`,
  `fichero-engine/src/fichero/workflows/tasks.py`,
  `fichero-engine/src/fichero/actions/registry.py`,
  `fichero-engine/src/fichero/providers.py`, and
  `fichero-engine/src/fichero/authz.py`.
- Confirmed `~/.venv/bin/mkdocs build --strict` passes.
