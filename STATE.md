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

## Next Session — Start Here

1. **All 0.0.2 blocked** — session pivoted to 0.0.3 worktree. Two 0.0.3 tasks completed: #618 (sidebar indentation) and #602 (sibling reorder).
2. **0.0.3 next tasks:** #617 (toolbar redesign, large), #593 (swipe navigation, complex). Both need visual testing.
3. **0.0.2 blockers still open** — Daniel must: verify #598 on-device, pick PDF architecture for #595, provide Sparkle certs for #520.
4. Do NOT start 0.0.4 until Daniel approves 0.0.2.

---

*Last updated: 2026-04-22* — No unblocked 0.0.2 work. Pivoted to 0.0.3; completed #618 + #602.
