# STATE.md — Fichero

Last updated: 2026-02-28

## Current Branch

`codex/restructure-api-swiftui` (173 commits ahead of main)

## This Week's Focus

Phase 0: Planning — no coding yet. Audit features, design flag system, build milestone plan.

## In Progress

| Issue | Task | Status |
|---|---|---|
| — | — | — |

## Blocked

- Feature flag system: needs design decision (compile-time vs. runtime)
- v1.0 scope: needs Daniel input on what's in vs. out

## Next Session — Start Here

1. Read `docs/agent-workflow/TODO.md` for current task list
2. Check git log: `git log --oneline -20`
3. Pick up Phase 0 work: feature audit or milestone plan

## Dev Environment

```bash
PYTHONPATH=fichero-api/src .venv/bin/uvicorn fichero.api.main:app --port 8765   # start backend
PYTHONPATH=fichero-api/src .venv/bin/pytest fichero-api/tests/unit/ --ignore=fichero-api/tests/unit/_archived   # run tests
swiftlint lint fichero-swiftui/fichero-swiftui/   # swift lint
ruff check fichero-api/src/   # python lint
```

Status: READY (verified 2026-02-26)
