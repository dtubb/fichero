# Release Surface — Fichero 0.0.1

**Created:** 2026-03-02
**Milestone:** M0 — Foundation
**Status:** Definitive reference for 0.0.1 gating

---

## Purpose

This document defines the exact feature surface for Fichero 0.0.1. It is the single source of truth agents and the team use when implementing feature gating, validating builds, and deciding what ships.

If a feature is not listed as `release` here, it must be gated off in the 0.0.1 build.

---

## Frontend Surface

### Sidebar Modes

| Mode | Tier | Notes |
|------|------|-------|
| **Library** | `release` | Document browser — grid, list, table views |
| **Search** | `release` | Full-text search interface |
| **Workflows** | `release` | Visual workflow editor (Added per Daniel) |
| Chat | `off` | AI conversation — requires providers |
| Batches | `off` | Batch processing UI |
| Automation | `off` | Schedules and triggers |
| Activity | `off` | Execution history |

### Other Frontend Features

| Feature | Tier | Notes |
|---------|------|-------|
| Documents (CRUD, inspector) | `release` | Core document management |
| Ingest (file import) | `release` | PDF, DOCX, images, etc. |
| Storage | `release` | Library storage layer |
| Settings | `release` | App settings panel |
| Folders | `release` | Folder hierarchy |
| Sidebar nav | `release` | Navigation chrome |
| Toolbars / Menu / Components / Sheets | `release` | UI infrastructure |
| **Providers** | `release` | Enabled in 0.0.1 (Added per Daniel) |
| **AI Providers UI** | `release` | Enabled in 0.0.1 (Added per Daniel) |
| **Workflows** | `release` | Enabled in 0.0.1 (Added per Daniel) |
| **Workflow Execution** | `release` | Enabled in 0.0.1 (Added per Daniel) |
| Chat | `off` | — |
| Activity | `off` | — |
| Batch | `off` | — |
| Actions | `off` | — |
| Agents | `off` | — |
| Automation | `off` | — |
| Integrations | `off` | — |
| MCP Servers | `off` | — |
| Chains | `off` | — |
| Schedules | `off` | — |
| Triggers | `off` | — |
| Local Models | `off` | — |
| Model Comparison | `off` | — |
| Models (HuggingFace) | `off` | — |

---

## Backend Route Groups

### `release` — Included in 0.0.1

| Route Group | Description |
|-------------|-------------|
| `documents` | Document CRUD, listing, metadata |
| `search` | Full-text and saved searches |
| `ingest` | File ingestion pipeline |
| `storage` | Library storage operations |
| `folders` | Folder hierarchy CRUD |
| `health` | Health check endpoint |
| `stats` | Library statistics |
| `settings` | App configuration |
| `artifacts` | Document artifacts |
| **`providers`** | LLM provider management (Added per Daniel) |
| **`models`** | Model listing per provider (Added per Daniel) |
| **`workflows`** | Workflow CRUD (Added per Daniel) |
| **`workflow-execution`** | Workflow run + SSE streaming (Added per Daniel) |

### `dev` — Accessible when `FICHERO_FEATURE_TIER=dev`

| Route Group | Description |
|-------------|-------------|
| — | — |

### `off` — Disabled in 0.0.1

| Route Group | Description |
|-------------|-------------|
| `chat` | AI conversation endpoints |
| `batch` | Batch processing |
| `activity` | Execution history |
| `schedules` | Cron-based automation |
| `triggers` | File system triggers |
| `integrations` | Third-party app bridge |
| `actions` | Workflow actions |
| `mcp-servers` | MCP server management |
| `model-comparison` | Side-by-side model eval |
| `chains` | Workflow chaining |
| `local-models` | Local model management |

---

## Feature Gating Mechanism

### Frontend (Swift)

**File:** `FeatureFlags.swift` (`fichero/fichero/App/FeatureFlags.swift`)

- Singleton `FeatureManager` controls all frontend flags.
- Each flag backed by `AppStorage` for per-flag persistence.
- `FICHERO_ALL_FEATURES` environment variable enables everything (development override).
- Sidebar modes, menu items, and navigation routing check flags before rendering.

### Backend (Python)

**File:** `feature_flags.py` (`fichero-engine/src/fichero/feature_flags.py`)

- `FICHERO_FEATURE_TIER` environment variable controls the active tier.
- Default: `release` (only release routes are registered).
- Set to `dev` to also enable dev-tier routes.
- Route registration in `main.py` checks the tier before including route groups.

---

## Acceptance Gate

The 0.0.1 release is accepted when all of the following pass:

1. `xcodebuild -scheme fichero -destination 'platform=macOS' build` exits 0
2. `PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/ --ignore=fichero-engine/tests/unit/_archived` passes with 0 failures
3. `swiftlint lint fichero/fichero/` produces 0 errors
4. `PYTHONPATH=fichero-engine/src .venv/bin/ruff check fichero-engine/src/` produces 0 errors
5. Hidden features (Chat, Batches, Automation, Activity) do not appear in the sidebar
6. Off-tier backend routes return 404 when `FICHERO_FEATURE_TIER=release`
7. Dev-tier routes (providers, models) are accessible when `FICHERO_FEATURE_TIER=dev`

---

## Validation Commands

Run these four commands to validate a 0.0.1 candidate:

```bash
# 1. Swift lint
swiftlint lint fichero/fichero/

# 2. Xcode build
xcodebuild -project fichero/fichero.xcodeproj -scheme fichero -configuration Debug -sdk macosx build

# 3. Python lint
PYTHONPATH=fichero-engine/src .venv/bin/ruff check fichero-engine/src/

# 4. Python tests
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/ --ignore=fichero-engine/tests/unit/_archived
```

All four must pass with zero errors before the release is shipped.
