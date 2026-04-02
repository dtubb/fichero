# STATE.md — Fichero

Last updated: 2026-04-02

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
| **1** | 1-4 | Knowledge Graph Core + PyKEEN | #387 | ✅ Backend complete |
| **2** | 5 | Hermeneutics (Interpretation) | #388 | ✅ Complete |
| **3** | 6 | Mind Palace + RealityKit | #389 | ✅ Complete |
| **4** | 0 | Agent Research (Sandboxed) | #390 | ✅ Backend + workflow tools |
| **5** | All | Integration & Polish | #391 | Planned |

## This Week's Focus

- Phases 1-3 backend (models + routes + MCP) complete
- Remaining: PyKEEN ML backend, then full SwiftUI views for all phases

## In Progress

- Phase 4 Agent Research (Layer 0): ✅ Backend complete, workflow tools added
  - research_web_search, research_browser_navigate, research_document_fetch as workflow tools
  - MCP tools (research agents) already present in mcp_server.py
  - Remaining: LangGraph agent composition for autonomous research

## Blocked

- None

## Next Session — Continue Here

**Phase 1 deferred: PyKEEN Integration + SwiftUI Views**

1. PyKEEN ML: `pykeen` not in dependencies — requires pip install + training pipeline
2. SwiftUI views: ClaimInspectorView, OntologyBrowserView, InterpretationPanelView, MindPalaceView
3. Quality gates: swiftlint + xcodebuild for each view

**Also:**
- After SwiftUI work: Phase 4 Agent Research (#390)

**Quality Gates:** ruff check + pytest at each step

## Session 2026-04-02 — Completed

- **#381 Gate Map**: Created `docs/0.0.2-planning/GATE-MAP.md` — full gate matrix across all 7 layers
  - Key finding: all Layers 0-6 are in dev tier, nothing promoted to release
  - SwiftUI tier gating not yet implemented
- **OpenAPI sync fix**: `export_openapi_schema.py` now uses `FICHERO_FEATURE_TIER=dev` → 226 endpoints/20 resources (was 125/16)
- SwiftLint 72 sorted-import warnings: codebase-wide issue, skipped (no clear convention to apply)
