# STATE.md — Fichero

Last updated: 2026-03-04

## Current Branch

`origin/main`

## This Week's Focus

Post-approval roadmap handoff:

- keep the local plan and GitHub roadmap aligned
- start M0 from the `0.0.1 - Core Library` milestone queue
- maintain the feature-gated release model as implementation begins

## Completed This Session

| Issue | Task | Result |
|---|---|---|
| `#231` | Define exact `0.0.1` release surface | Merged to main — `docs/agent-workflow/RELEASE_SURFACE_0.0.1.md` |
| `#232` | Implement frontend feature gating for `0.0.1` | PR #259 — ready for review |
| `#233` | Implement backend feature gating for `0.0.1` | PR #260 — ready for review |

## In Progress

| Issue | Task | Status |
|---|---|---|
| `#234` | Gate hidden sidebar surfaces cleanly | Queued (after #232 merges) |
| `#235` | Gate hidden menu and action surfaces cleanly | Queued (after #232 merges) |

## Operating Notes

- `Providers` decision resolved: stays `dev` tier for 0.0.1, promoted in 0.0.2
- Future roadmap now includes `0.2.0 - Spatial Knowledge Layer` (issues `#265`-`#274`); this is explicitly post-`0.1.0` work and not part of the `0.0.1` release surface
- Pytest not installed in `.venv` — needs `pip install pytest` before validation gates can run
- After #260 merges: run `./fichero-api/scripts/sync_openapi_schema.sh` to regenerate Swift OpenAPI client

## Next Session — Start Here

1. Review and merge PRs #259 and #260
2. After merges: run OpenAPI sync (`./fichero-api/scripts/sync_openapi_schema.sh`)
3. Pick up `#234` (sidebar gating) and `#235` (menu/action gating)
4. Fix pytest environment: `pip install pytest` in `.venv`

## Dev Environment

```bash
PYTHONPATH=fichero-api/src .venv/bin/uvicorn fichero.api.main:app --port 8765
PYTHONPATH=fichero-api/src .venv/bin/pytest fichero-api/tests/unit/ --ignore=fichero-api/tests/unit/_archived
PYTHONPATH=fichero-api/src .venv/bin/ruff check fichero-api/src/
swiftlint lint fichero-swiftui/fichero-swiftui/
xcodebuild -project fichero-swiftui/fichero-swiftui.xcodeproj -scheme fichero-swiftui -configuration Debug -sdk macosx build
```

Status: ready to use as the M0 validation gate
