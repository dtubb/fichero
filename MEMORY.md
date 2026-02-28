# MEMORY.md — Fichero

Last updated: 2026-02-28

## Current Phase

**Phase 0: Planning.** No coding until the plan is approved. Focus: feature audit, feature flags, milestone plan.

## Project State

- **Repo:** ~/code/fichero
- **Branch:** codex/restructure-api-swiftui (173 commits ahead of main)
- **Previous workspace:** ~/.openclaw/workspace-fichero-assistant/ (migrated — files preserved there)

## Architecture Summary

```
SwiftUI App → HTTP localhost:8765 → FastAPI → DuckDB/LanceDB
                                             → LangGraph (workflows)
                                             → LiteLLM (100+ providers)
```

- Frontend: pure SwiftUI, 343 Swift files (189 app + 16 generated services)
- Backend: FastAPI, 116 Python files, 8 route modules
- Bridge: OpenAPI-generated type-safe client

## Key Problem

Many features exist in various states of completion. Need to:
1. Audit what exists (what works, what doesn't, what's tested)
2. Design a feature flag system (dev vs release toggles)
3. Create a milestone plan with achievable targets
4. Stabilize before adding more

## Technical Priorities

1. Feature audit
2. Feature flag system design
3. Milestone plan (path to v1.0)
4. Then: OpenAPI migration, large file refactoring, lint compliance

## Dev Environment (verified 2026-02-26)

- Python .venv: READY (Python 3.14.3, `pip install -e "fichero-api/[dev]"`)
- swiftlint: INSTALLED (via Homebrew)
- Xcode: present (xcodebuild available)
- git/gh: working
- PYTHONPATH: must be set to `fichero-api/src`

## Conventions

- Commit format: conventional commits (`fix:`, `feat:`, `style:`, `test:`, `docs:`, `chore:`, `refactor:`)
- Branch naming: `feature/<name>`, `codex/<name>`, `fix/<name>`
- Tasks: Claude Code Tasks (primary) + `TASKS.md` (session view) + `docs/agent-workflow/TODO.md` (repo)
- Generated types: use `Components.Schemas.*` directly, avoid manual shadow types
- Backend port: 8765 (hardcoded in Swift APIClient)

## Lessons Learned

- Always check git branch before starting — must be on `codex/restructure-api-swiftui`
- Always run /build-and-test before marking anything complete
- Generated files are strictly read-only — never edit manually

## Memory Files

Detailed notes in `memory/`:
- `lessons.md` — mistakes and corrections
- `team-decisions.md` — decisions made during team sessions
- `constitution-changelog.md` — every constitution change with rationale
- `2026-02-26.md` — first session log
