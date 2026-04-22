# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — UI polish sprint done. Working through remaining non-blocking tasks, then closing out the milestone.

**Goal:** Complete non-blocking 0.0.2 tasks → release 0.0.2 → merge main into 0.0.3 and continue there.

## Open Issues (0.0.2 milestone)

| # | Title | Status |
|---|---|---|
| #653 | Activity view: current run not selectable | Non-blocking bug — do this |
| #651 | Sidebar: Workflows + Activity divider | Partially done (icons); divider TBD — do this |
| #650 | Workflows sidebar: single 'Workflows' row → list view | Non-blocking task — do this |
| #644 | Sidebar: 'Library' header → clickable icon + name row | Non-blocking task — do this |
| #619 | Backend connection slow on launch | Needs Daniel on-device profiling to diagnose |
| #605 | App startup slow | Needs Daniel on-device with Instruments |
| #520 | Sparkle auto-update | Needs Daniel's SPARKLE_FEED_URL + SPARKLE_PUBLIC_ED_KEY |

## Release Readiness

0.0.2 is basically ready. Three items are blocked on Daniel:
- **#619/#605** — perf issues we can't fix without on-device measurements
- **#520** — Sparkle needs Daniel's cert/feed URL

If startup feels acceptable in practice and Sparkle can wait for a patch, we can ship.

## Next Session — Start Here

1. **Do non-blocking tasks in order:** #644 → #650 → #651 → #653
2. **When those are done**, ask Daniel: are #619/#605 acceptable? Do you have Sparkle creds for #520?
3. **If yes to shipping**: create 0.0.2 PR → merge to main → `git fetch && git merge main` in 0.0.3 worktree
4. **0.0.3 first step** after merge: run build + tests to confirm clean baseline, then pick up 0.0.3 issues
5. 0.0.3 worktree at `~/code/fichero-0.0.3` — #618 (sidebar indentation) + #602 (sibling reorder) already done there

---

*Last updated: 2026-04-22* — Non-blocking task list clarified; release path documented.
