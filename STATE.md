# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — pushed and clean.

**Active worktrees:**
- `~/code/fichero-0.0.2` — all bugs fixed, Daniel testing
- `~/code/fichero-0.0.3` — Wire: Search v1 (Claude loop, branch `0.0.3`)

**Status:** 0.0.2 bug fix marathon complete. 18 bugs closed. Only #520 (Sparkle auto-update) remains.

## In Progress

Nothing active. All 0.0.2 bugs are closed.

## Test Health

**183 passing (167 existing + 16 new), 14 pre-existing failures (missing endpoints.json/contract fixtures).**

## Next Session — Start Here

1. **Daniel: test 0.0.2** — verify sidebar, inspector, preview, drag-drop, settings, magnifier
2. **#520 (Sparkle):** verify auto-update is wired (Check for Updates menu item, appcast URL in Info.plist)
3. **When 0.0.2 is approved:** `/release 0.0.2`, then rebase 0.0.3 onto it
4. **In `~/code/fichero-0.0.3`:** run `/session-start-auto` to build Wire: Search v1

## Parallel Workflow

Daniel tests N → Claude builds N+1 in a separate worktree.
Gate: Claude never merges without Daniel's `/release N`.

---
*Last updated: 2026-04-16* — 18 bugs closed (#525-#543, #353, #385, #386); #520 Sparkle remains
