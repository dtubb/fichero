# STATE.md — Fichero

Last updated: 2026-03-08

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
| `#234` | Gate hidden sidebar surfaces cleanly | Closed. Branch `feature/issue-234` pushed with persisted-mode sanitization and hidden-mode fallback guards. |

## In Progress

| Issue | Task | Status |
|---|---|---|
| `#235` | Gate hidden menu and action surfaces cleanly | Next up |

## Operating Notes

- `Providers` decision resolved: stays `dev` tier for 0.0.1, promoted in 0.0.2
- Future roadmap now includes `0.2.0 - Spatial Knowledge Layer` (issues `#265`-`#274`); this is explicitly post-`0.1.0` work and not part of the `0.0.1` release surface
- Python tooling path drift: `.venv/bin/python`, `.venv/bin/ruff`, and `.venv/bin/pytest` were not present in this session environment
- After #260 merges: run `./fichero-api/scripts/sync_openapi_schema.sh` to regenerate Swift OpenAPI client
- `xcodebuild` currently fails via the `SwiftLint` run script in Xcode phase (could not open `.swiftlint.yml`, then "No lintable files found")

## Next Session — Start Here

1. Open PR from `feature/issue-234` and merge after review
2. Pick up `#235` (menu/action gating)
3. Fix local Python environment so `.venv/bin/python` exists in sessions; then rerun `ruff` and `pytest`
4. Fix Xcode SwiftLint run-script path/config behavior, then rerun `xcodebuild`

## Dev Environment

```bash
PYTHONPATH=fichero-api/src .venv/bin/uvicorn fichero.api.main:app --port 8765
PYTHONPATH=fichero-api/src .venv/bin/pytest fichero-api/tests/unit/ --ignore=fichero-api/tests/unit/_archived
PYTHONPATH=fichero-api/src .venv/bin/ruff check fichero-api/src/
swiftlint lint fichero-swiftui/fichero-swiftui/
xcodebuild -project fichero-swiftui/fichero-swiftui.xcodeproj -scheme fichero-swiftui -configuration Debug -sdk macosx build
```

Status: ready to use as the M0 validation gate
