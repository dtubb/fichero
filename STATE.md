# STATE.md — Fichero

Last updated: 2026-04-01

## Current Branch

`codex/0.0.2-planning` — 0.0.2 knowledge graph implementation worktree.

## Source of Truth

- **GitHub Milestone:** [0.0.2 - Search + Semantic Foundation](https://github.com/dtubb/fichero/milestone/8)
- **GitHub Issues:** https://github.com/dtubb/fichero/issues
- **Project board:** https://github.com/users/dtubb/projects/5
- **Active Plan:** `docs/agent-workflow/PLAN-0.0.2-knowledge-graph.md` (comprehensive 7-layer architecture)

## GitHub Issues Created

| Issue | Phase | Layer | Title |
|-------|-------|-------|-------|
| #387 | 1 | 1-4 | Knowledge Graph Core + PyKEEN |
| #388 | 2 | 5 | Hermeneutics |
| #389 | 3 | 6 | Mind Palace + RealityKit |
| #390 | 4 | 0 | Agent Research |
| #391 | 5 | All | Integration & Polish |

## Implementation Order (Step-by-Step)

**Principle:** Layer-by-layer, fully integrated (models → routes → MCP → SwiftUI → tests) before proceeding.

| Phase | Layer | Focus | Issue | Status |
|-------|-------|-------|-------|--------|
| **1** | 1-4 | Knowledge Graph Core + PyKEEN | #387 | **Next** |
| **2** | 5 | Hermeneutics (Interpretation) | #388 | Planned |
| **3** | 6 | Mind Palace + RealityKit | #389 | Planned |
| **4** | 0 | Agent Research (Sandboxed) | #390 | Planned |
| **5** | All | Integration & Polish | #391 | Planned |

## This Week's Focus

- **Phase 1: Layers 1-4** — Begin immediately
- Multi-source claims with ontology/epistemology
- PyKEEN link prediction (NOT deferred)
- Each component: models → routes → MCP → SwiftUI → tests

## In Progress

- Final plan review complete
- GitHub issues created and milestoned
- Ready to begin Phase 1 implementation (#387)

## Blocked

- None

## Next Session — Start Here

**Phase 1: Layers 1-4 — Knowledge Graph Core (#387)**

1. Activate `.venv`: `source ~/code/fichero-0.0.2/.venv/bin/activate`
2. Start backend: `PYTHONPATH=fichero-api/src uvicorn fichero.api.main:app --port 8765 --reload`
3. Begin with models (`knowledge_models.py`):
   - Add `SourceType`, `ClaimType`, `EpistemicStatus` enums
   - Add prediction metadata models
   - Update `KnowledgeClaim` with multi-source support
4. Run quality gates: `ruff check` + `pytest`
5. Continue with migration script → routes → PyKEEN → MCP → SwiftUI

**Quality Gates:** Run at EACH step — ruff, pytest, swiftlint, xcodebuild
