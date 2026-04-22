# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — all bug-fix issues reviewed this session.

**Goal:** Awaiting Daniel's input on remaining 0.0.2 blockers before milestone can close.

## Open Issues (0.0.2 milestone)

| # | Title | Notes |
|---|---|---|
| #619 | Backend connection slow on launch | OSLog ⏱ instrumentation in; needs Daniel to profile on-device |
| #607 | Can't reorder folder in sidebar | Deprioritized by Daniel ("sort of works, can leave it") |
| #605 | App startup slow | Needs Daniel on-device with Instruments |
| #598 | Sidebar drag-drop lands on wrong row | Fix committed 31b6c53a — needs Daniel on-device verify |
| #595 | PDF one-page + swipe navigation | Architecture choice pending: Daniel must pick Option 1, 2, or 3 from issue comments |
| #520 | Sparkle auto-update integration | Needs SPARKLE_FEED_URL + SPARKLE_PUBLIC_ED_KEY in xcconfig |

## Resolved This Session

- Confirmed #623 (drag-out sidebar), #624 (JPG PIL regression), #625 (JSON preview) were all fixed in prior commits and properly closed.
- All were already committed on 0.0.2 branch.

## Next Session — Start Here

1. **#595** — Ask Daniel to pick Option 1, 2, or 3 from the issue. Option 1 is lightest. Once he picks, implementation can proceed immediately.
2. **#598** — Ask Daniel to verify sidebar drag-drop on-device (drop highlight + target row correctness). If confirmed working, close.
3. **#619/#605** — Run: `/usr/bin/log stream --predicate 'eventMessage CONTAINS "⏱"'` during app launch. Report the timing output to identify the bottleneck.
4. Do NOT start 0.0.3 until Daniel approves 0.0.2 (STATE.md rule — overrides CLAUDE.md two-ahead default per session guidance).

---

*Last updated: 2026-04-22* — Audit session. Confirmed all recent bug fixes landed; triaged remaining open issues. All blocked on Daniel's input.
