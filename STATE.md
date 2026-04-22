# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — UI polish sprint complete. Awaiting Daniel to test on-device.

**Goal:** Daniel verifies remaining open issues; milestone closes when blockers resolve.

## Open Issues (0.0.2 milestone)

| # | Title | Notes |
|---|---|---|
| #653 | Activity view: current run not selectable | Backend may lock during execution; needs investigation |
| #651 | Sidebar Workflows + Activity divider | Icons added (#644); divider treatment TBD |
| #619 | Backend connection slow on launch | OSLog ⏱ instrumentation in; needs Daniel to profile on-device |
| #605 | App startup slow | Needs Daniel on-device with Instruments |
| #520 | Sparkle auto-update integration | Needs SPARKLE_FEED_URL + SPARKLE_PUBLIC_ED_KEY in xcconfig |

## Next Session — Start Here

1. **Check #653** — Activity view current run not selectable; may be a backend lock during workflow execution.
2. **Check #651** — Divider between Workflows and Activity sections in sidebar; icons done, spacing/divider TBD.
3. **Ask Daniel** if he's tested any open issues on-device (#619, #605).
4. If all 0.0.2 issues resolved → create milestone PR and merge; then start 0.0.3 proper.
5. 0.0.3 worktree at `~/code/fichero-0.0.3` — #618 (sidebar indentation) and #602 (sibling reorder) already done there.

---

*Last updated: 2026-04-22* — UI polish sprint done (#643, #656, #569, #654, #641, #640, #607, #598 closed).
