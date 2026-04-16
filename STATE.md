# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — pushed and clean.

**Active worktrees:**
- `~/code/fichero-0.0.2` — bug fixes, Daniel testing
- `~/code/fichero-0.0.3` — Wire: Search v1 (Claude loop, branch `0.0.3`)

**Status:** All type:bug issues on 0.0.2 milestone closed. Only #520 (Sparkle task) remains. Ready for Daniel to verify before release.

## In Progress

Nothing active.

## Test Health

**190+ passing, 13 pre-existing failures** (missing `endpoints.json` at test runtime + missing `export_api_schemas.py` script — infrastructure issues, not code).

## Next Session — Start Here

1. **Daniel: relaunch and verify this round's fixes** — pinch-to-zoom, sidebar arrow keys, Option+Left/Right pane cycling, middle-truncated filenames, magnifier Y direction, Quick Look removal.
2. **#520 Sparkle** — verify Check-for-Updates menu item + appcast URL.
3. **If all clean:** `/release 0.0.2`, then rebase 0.0.3 onto it.
4. **In `~/code/fichero-0.0.3`:** resume Wire: Search v1 (`/session-start-auto`).

## Parallel Workflow

Daniel tests N → Claude builds N+1 in a separate worktree.
Gate: Claude never merges without Daniel's `/release N`.

---
*Last updated: 2026-04-16 (late evening)* — 30+ bugs closed this session. Only #520 remains.
