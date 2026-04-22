# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — #639, #635, #633 closed this session.

**Goal:** Close remaining open issues on 0.0.2 milestone via autonomous loop.

## Open Issues (0.0.2 milestone)

| # | Title | Notes |
|---|---|---|
| #619 | Backend connection slow on launch | OSLog ⏱ instrumentation already in; needs Daniel to profile on-device |
| #607 | Can't reorder folder in sidebar | Drag-drop — needs investigation |
| #605 | App startup slow | Perf investigation |
| #598 | Sidebar drag-drop lands on wrong row | Fix shipped in 31b6c53a — on-device verify needed |
| #595 | PDF one-page + swipe navigation | Architecture call — 3 options in issue |
| #520 | Sparkle auto-update integration | Needs SPARKLE_FEED_URL + SPARKLE_PUBLIC_ED_KEY in xcconfig |

## Next Session — Start Here

1. **First pick**: #607 (can't reorder folder in sidebar) — drag-drop bug investigation.
2. #619 and #605 need Daniel to run the app with OSLog instrumentation to profile; skip until he does.
3. #598 may already be fixed (31b6c53a) — check issue comments / ask Daniel before re-working.
4. #595 needs an architecture decision from Daniel before implementing.
5. Do NOT start 0.0.3 until Daniel approves 0.0.2.

---

*Last updated: 2026-04-22* — Closed #639, #635, #633. 6 issues remain on 0.0.2.
