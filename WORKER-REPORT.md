# Worker Report

## 2026-06-28

- Extended [docs/contributor/node-model.md](/Users/danieltubb/code/fichero-worktrees/ms-docs/docs/contributor/node-model.md) with the shipped research-workspace fold.
- Verified against merged code in `fichero-engine/src/fichero/db.py`, `fichero-engine/src/fichero/research_models.py`, `fichero-engine/src/fichero/api/routes/research_crud.py`, `fichero-engine/src/fichero/workflows/task_types.py`, and the related unit tests.
- Captured the current boundary explicitly:
  - `ResearchProject` is mirrored into a workspace `Document` with `prototype_key="research_workspace"`
  - `ResearchPlan`, `ResearchTask`, and `ResearchStep` are still stored as their own models and are not yet folded into `Document` rows
  - `BackgroundTask` is workflow infrastructure, not part of the node-model fold
- Gate: `~/.venv/bin/mkdocs build --strict` passed.
