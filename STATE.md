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

1. **Daniel: test sidebar drag-drop end-to-end** — Finder→folder (highlight expected), Finder→leaf (lighter highlight, imports as sibling), Finder→between rows at any level (blue line), grid→sidebar folder (existing `.draggable(doc.id)` path).
2. **#556 settings layout** — still broken; reopened with root-cause fix plan (remove inner `.frame(width: 550, height: 450)` at `GeneralSettingsView.swift:114` + audit other settings tabs).
3. **#570 drag-drop PDF invisible in sidebar** — regression in c3ad9d24; debug checklist in the issue body (curl `/api/documents` after drop first).
4. **#572 manual reorder persistence** — needs `Document.sort_order` backend column + migration; tracked for 0.0.6.
5. **#520 Sparkle** — last untouched 0.0.2 item.

## Parallel Workflow

Daniel tests N → Claude builds N+1 in a separate worktree.
Gate: Claude never merges without Daniel's `/release N`.

---
*Last updated: 2026-04-16 (evening, post PDF-as-container)* — #568, #566, #567 closed; Swift test coverage added for PDF navigation + per-page thumbnail rendering. Only #520 remains on 0.0.2.
