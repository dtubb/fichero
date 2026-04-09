# MEMORY.md — Fichero

Last updated: 2026-04-09

## Current Phase

**0.0.2 Knowledge Graph Implementation.** Active development in `~/code/fichero-0.0.2` worktree.

Seven-layer architecture:
- Layer 0: Agent Research (sandboxed agents with web/browser tools)
- Layers 1-4: Knowledge Graph Core (sources → claims → ontology → epistemology)
- Layer 5: Hermeneutics (interpretation, patterns, meaning)
- Layer 6: Mind Palace (3D visual + text assembly)

## Project State

- **Repo:** `~/code/fichero-0.0.2` (0.0.2 planning worktree)
- **Branch:** `codex/0.0.2-planning`
- **Current release target:** 0.0.2 — Knowledge Graph with full research-to-synthesis pipeline
- **Active plan:** `docs/agent-workflow/PLAN-0.0.2-knowledge-graph.md`

## Architecture Summary

```text
Layer 0: Agent Research → Web search, browser, systematic discovery
     ↓
Layer 1: Sources → Documents, archives, web captures
     ↓
Layer 2: Claims → Atomic statements with multi-source provenance
     ↓
Layer 3: Ontology → Entity-centric "bio" views
     ↓
Layer 4: Epistemology → Evidence relationships (supports/contradicts/refines)
     ↓
Layer 5: Hermeneutics → Interpretation, patterns, meaning
     ↓
Layer 6: Mind Palace → Visual + text assembly workspace
```

## Technical Priorities

1. Layer 0: Agent Research infrastructure with sandboxed tools
2. Layer 5: Hermeneutics models (interpretive frameworks, patterns)
3. Layer 6: Mind Palace models (spatial, notes, viewport)
4. Complete Layers 1-4: Multi-source claims, ontology, PyKEEN
5. MCP tools for all layers (agent control)
6. SwiftUI implementation for Research, Hermeneutics, and Mind Palace

## Validation Standard

For each layer:
- Models defined with Pydantic v2
- API routes with FastAPI
- Unit tests with pytest
- OpenAPI schema sync
- Swift client generation
- SwiftUI views

## Conventions

- Commit format: conventional commits
- Branch naming: `feature/<name>`, `codex/<name>`, `fix/<name>`
- Generated files are read-only; regenerate instead of editing
- `PYTHONPATH=fichero-api/src` for all Python commands
- PyKEEN is installed and importable in the project environment; use real PyKEEN training/evaluation for `/predictions/generate/pykeen`, not simulated metrics
- Sandboxed agent tools (no filesystem/CLI escape)
- **Quality gates at each step:**
  - `ruff check fichero-api/src/` — Python linting
  - `python -m pytest fichero-api/tests/unit/` — Python tests
  - `swiftlint lint fichero-swiftui/fichero-swiftui/` — Swift linting
  - `xcodebuild -project fichero-swiftui/fichero-swiftui.xcodeproj -scheme Fichero -sdk macosx build` — Swift build
  - Activate `.venv`: `source ~/code/fichero-0.0.2/.venv/bin/activate`
  - Run backend: `PYTHONPATH=fichero-api/src uvicorn fichero.api.main:app --port 8765 --reload`

## Feature Gating Architecture

### Backend (Python)
- Gating lives in `fichero-api/src/fichero/api/main.py` via `FICHERO_FEATURE_TIER` env var
- Layer 0-6 routes registered under `dev` tier initially
- Promote to `release` tier after validation

## GitHub Roadmap

- Milestone: `0.0.2 - Providers` (to be renamed to reflect knowledge graph focus)
- Issues to be created for each layer implementation
- Cross-layer integration tracked in project board

## Memory Files

Detailed notes in `memory/`:
- `constitution-changelog.md`
- `2026-02-26.md`
- `proposals/`
