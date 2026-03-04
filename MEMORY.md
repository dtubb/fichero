# MEMORY.md — Fichero

Last updated: 2026-03-02

## Current Phase

**M0 ready.** The release plan is approved and the roadmap is published.

Current focus:

1. execute the `0.0.1` milestone queue
2. keep the constitution and roadmap aligned
3. maintain the feature-gated release model as implementation begins

## Project State

- **Repo:** `~/code/fichero`
- **Branch:** `main`
- **Current release target:** make `0.0.1` the first stable, limited release

## Architecture Summary

```text
SwiftUI App -> HTTP localhost:8765 -> FastAPI -> DuckDB/LanceDB
                                            -> LangGraph
                                            -> LiteLLM/providers
```

- Frontend: native macOS SwiftUI app
- Backend: Python FastAPI
- Contract: OpenAPI-generated Swift client

## Key Problem

The codebase contains more surfaced features than can safely ship at once.

The correct release strategy is:

1. define feature tiers (`release`, `beta`, `dev`, `off`)
2. ship only the trustworthy surface in `0.0.1`
3. promote features one release at a time
4. keep frontend and backend aligned as features move tiers

## Technical Priorities

1. Implement M0 against the approved `0.0.1` surface
2. Keep the local plan and GitHub roadmap in sync as implementation progresses
3. Preserve the feature-tier model while implementation begins
4. Prepare the `0.0.2` provider promotion path without broadening `0.0.1`

## Validation Standard

For the approved implementation surface, the required checks are:

- `swiftlint lint fichero-swiftui/fichero-swiftui/`
- `xcodebuild -project fichero-swiftui/fichero-swiftui.xcodeproj -scheme fichero-swiftui -configuration Debug -sdk macosx build`
- `PYTHONPATH=fichero-api/src .venv/bin/ruff check fichero-api/src/`
- `PYTHONPATH=fichero-api/src .venv/bin/pytest fichero-api/tests/unit/ --ignore=fichero-api/tests/unit/_archived`

## Conventions

- Commit format: conventional commits
- Branch naming: `feature/<name>`, `codex/<name>`, `fix/<name>`
- Generated files are read-only; regenerate instead of editing
- `PYTHONPATH=fichero-api/src` for all Python commands
- Significant API changes are cross-stack changes

## Feature Gating Architecture

### Frontend (Swift)
- `FeatureManager.swift` — singleton `@MainActor` class, `AppStorage`-backed flags
- Env var `FICHERO_ALL_FEATURES=1` overrides all flags for dev builds
- Env var `FICHERO_FEATURE_TIER=dev` enables dev-tier features (providers)
- 0.0.1 defaults: Library ✅, Search ✅, Chat ❌, Workflows ❌, Batches ❌, Automation ❌, Activity ❌, Providers (dev only)
- `resetToV001()` is the canonical reset method

### Backend (Python)
- Gating lives in `fichero-api/src/fichero/api/main.py` via `FICHERO_FEATURE_TIER` env var
- Default tier: `release` — only core routes registered
- `dev` tier adds providers + models routes
- Off-tier routes are deregistered and documented inline for future promotion
- After any backend route change: run `./fichero-api/scripts/sync_openapi_schema.sh`

## Lessons Learned

- Do not trust stale state docs; reconcile them before acting on them
- Feature gating is the release mechanism, not a side concern
- The first question is not "can this be built?" but "what tier should this feature live in right now?"
- GitHub can drift behind the local roadmap; roadmap work includes cleanup and migration, not just creating new milestones and issues
- Once the roadmap is published, the main docs must be rewritten into post-approval language quickly or they will continue to mislead agents
- Cross-release umbrella issues are acceptable when they are explicitly documented; `#113` stays unmilestoned by design while concrete QA issues are tied to release milestones
- Frontend-only feature flag changes do not require cross-stack review; only OpenAPI contract changes do
- `pytest` is not installed in `.venv` — use `python -m pytest` or install it; the validation commands in CLAUDE.md assume `.venv/bin/pytest` which does not exist

## GitHub Roadmap

Seeded on 2026-03-02:

- Milestones created: `0.0.1 - Core Library`, `0.0.2 - Providers`, `0.0.3 - Chat Beta`, `0.0.4 - Workflows Beta`, `0.0.5 - Operations`, `0.1.0 - Coherent AI Layer`
- Issues created: `#231` through `#258`
- Legacy planning issues closed as superseded: `#222` through `#229`
- Legacy open milestones closed: `0.1.0-dev`, `0.1.1-dev`, `0.1.3-dev`
- Existing issue `#220` was folded into `0.0.1 - Core Library`
- Existing QA issues `#114`, `#116`, and `#117` were aligned to `0.0.1`; `#115` was aligned to `0.0.4`
- `#113` remains the explicit cross-release QA umbrella and is intentionally left unmilestoned

## Memory Files

Detailed notes in `memory/`:

- `constitution-changelog.md`
- `2026-02-26.md`
- `proposals/`
