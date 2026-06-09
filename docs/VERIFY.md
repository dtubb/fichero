# What `verify_all` checks (and what's still a gap)

The principle: **the more we check programmatically, the more we catch and the
cleaner it stays.** This is the authoritative checklist. ✅ in verify · ⚠️ exists
but not wired/enforced · ❌ not built yet (issue filed).

## Architecture / observable pattern
- ✅ **Endpoints are used** — no dead routes (`check_endpoint_usage.py`, #1920)
- ✅ **No direct endpoint calls in SwiftUI** — views go through @Observable stores (`check_view_endpoint_access.py`, #1911)
- ✅ **Logic in backend, no raw SQL outside db.py** (`test_db_access_guardrail.py`, #1876)
- ✅ **CLI ↔ SwiftUI ↔ OpenAPI** consume the same contract (`validate_model_sync.py` + endpoint matrix)
- ⏳ **Completeness matrices** — endpoint×{store,cli,swift}, undo coverage, CRUD per entity, action×{menu,context-menu,toolbar,keyboard} (#1925)

## Lint
- ✅ **Swift lint** (`swiftlint`)
- ✅ **Backend lint (`ruff`)** — `verify_all --fast` runs `ruff check fichero-engine/src/` via the configured Python module when available, otherwise the installed `ruff` binary (#1938)
- ⚠️ **swiftlint → zero ratchet** — ~60 warnings currently PASS; not enforced (#1915)

## Build
- ✅ **Swift build** (xcodebuild in `--full`; manager uses Xcode MCP `BuildProject` — a FULL build, since incremental greens mask cross-file errors)

## Tests
- ✅ **Backend unit tests** (CrossLanguageGate → verify_python.sh → pytest)
- ✅ **Swift unit tests** (xcodebuild test)
- ✅ **CLI live-contract tests** (#252)
- ⚠️ **GUI / XCUITest** (#1230) exists but is QUEUED — not run in verify → **#1939**
- ❌ **Test coverage is solid** — not everything is tested; enumerate gaps → issues (#1916, Test Coverage milestone)

## Mac-assed
- ✅ native controls (`check_native_controls.py`) · ✅ no-emoji/SF-Symbols/fonts (`check_no_emoji_sf_symbols.py`)
- ✅ comment hygiene (`check_comment_hygiene.py`) · ✅ feature-flag hygiene (`check_feature_flags.py`)

## Contract / release
- ✅ **OpenAPI sync** (`validate_model_sync.py`) · ✅ **version↔date** (`check_version_date.sh`, #1923)

## Project hygiene (NEW — the "dump folder" problem)
- ❌ **Folder organization** — flag Views/ (and backend) folders that are dumping grounds (too many files / mixed concerns / files that belong in a subfolder) → **#1940**
- ❌ **Xcode registration** — every `.swift` is registered via `add-swift-file.rb` (unregistered files = invisible to the compiler) → **#1941**
- ✅ **No finished-but-unmerged worker worktrees/branches** — `scripts/check_unmerged_work.py`, run by manager/integrator on demand; excluded from `verify_all --fast` because active worktree state is not a per-commit quality gate (#1942)

## Tiers (so we run the right depth)
`--fast` (seconds, scripts only) · `--standard` (+ backend pytest) · `--full` (+ xcodebuild test) · `profile` (Instruments + py-spy, on demand). #1910

## The loop
verify (fast) → **auto-file new failures to the right milestone, deduped** (#1919) →
worked in roadmap tier order → re-verify. Known errors are tracked issues, never
re-surfaced (token-cheap).
