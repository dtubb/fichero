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

1. **Daniel: import a multi-page PDF** and verify — grid shows one thumbnail per page rendered by `PDFThumbnailView`, double-clicking the PDF drills into it, preview pane shows the correct page full-size.
2. **Verify magnifier** — ⌘⌥[ zooms below 1x, ⌘⇧M toggles panel, ⌘⌥M toggles lock.
3. **#520 Sparkle** — last open 0.0.2 item. Needs SDK wire-up, appcast signing, update-check UI.
4. **If all clean:** `/release 0.0.2`, then rebase 0.0.3 onto it.
5. **In `~/code/fichero-0.0.3`:** resume Wire: Search v1 (`/session-start-auto`).

## Parallel Workflow

Daniel tests N → Claude builds N+1 in a separate worktree.
Gate: Claude never merges without Daniel's `/release N`.

---
*Last updated: 2026-04-16 (evening, post PDF-as-container)* — #568, #566, #567 closed; Swift test coverage added for PDF navigation + per-page thumbnail rendering. Only #520 remains on 0.0.2.
