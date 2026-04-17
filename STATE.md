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

1. **Daniel: verify #556 settings layout** — all 4 settings tabs now use `.formStyle(.grouped)`. Expected: proper grouped sections, left-aligned labels, nothing clipped. If still wrong, fresh screenshot.
2. **Daniel: verify #570 PDFs in sidebar** — drop a PDF → should appear as sidebar row with disclosure triangle; open it → pages listed as children sorted by page number.
3. **Daniel: test sidebar drag-drop end-to-end** — Finder→folder (blue wash), Finder→leaf (lighter wash, imports as sibling), Finder→between rows (native blue line), grid→sidebar folder (move).
4. **#520 Sparkle** — last untouched 0.0.2 item. Needs SDK wire-up + appcast signing + update-check UI.
5. **#572 (0.0.6)** — sort-order persistence once Daniel wants manual reordering to stick.

## Parallel Workflow

Daniel tests N → Claude builds N+1 in a separate worktree.
Gate: Claude never merges without Daniel's `/release N`.

---
*Last updated: 2026-04-16 (evening, post PDF-as-container)* — #568, #566, #567 closed; Swift test coverage added for PDF navigation + per-page thumbnail rendering. Only #520 remains on 0.0.2.
