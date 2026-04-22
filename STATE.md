# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — PR #638 merged. Activity view bug batch complete.

**Goal:** Close remaining open issues on 0.0.2 milestone via autonomous loop.

## Open Issues (0.0.2 milestone)

| # | Title | Notes |
|---|---|---|
| #639 | Settings: show default embeddings model + picker | Just filed — good autonomous target |
| #635 | Console log lacks filename per node | Needs backend logging change |
| #633 | Output Log checkmarks but no artifacts | Deep investigation needed |
| #619 | Backend connection slow on launch | OSLog ⏱ instrumentation already in; needs profiling |
| #607 | Can't reorder folder in sidebar | Drag-drop |
| #605 | App startup slow | Perf investigation |
| #598 | Sidebar drag-drop lands on wrong row | Fix shipped in 31b6c53a — on-device verify needed |
| #595 | PDF one-page + swipe navigation | Architecture call — 3 options in issue |
| #520 | Sparkle auto-update integration | Needs SPARKLE_FEED_URL + SPARKLE_PUBLIC_ED_KEY in xcconfig |

## Next Session — Start Here

1. **Auto loop target**: #639 (embeddings model in Settings) is well-scoped and actionable — good first pick.
2. For #598: may already be fixed (31b6c53a) — check issue comments before working on it.
3. #633 and #635 need backend investigation before implementing; read issue + trace code first.
4. PR workflow: push → `gh pr create` → `gh pr merge --merge` (Claude does all three).
5. Do NOT start 0.0.3 until Daniel approves 0.0.2.

---

*Last updated: 2026-04-22* — Activity bug batch merged. 9 issues remain on 0.0.2.
