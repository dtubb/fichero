# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — all autonomous items shipped. 3 feature branches await Daniel's review + merge. BLOCK.md written.

**Goal:** Daniel reviews and merges the 3 feature branches, then runs on-device verification sweep before cutting the release.

## Autonomous items — ALL DONE ✓

1. ~~**#622 icon/list grid column min-width** — DONE, merged to `0.0.2`~~ ✓
2. ~~**#594 close-as-skipped** — CLOSED~~ ✓
3. ~~**#619/#605 startup instrumentation** — DONE, open pending log analysis~~ ✓
4. ~~**#600 .mov drag-drop** — DONE, merged to `0.0.2`~~ ✓
5. ~~**#603 ingest-mode badges + delete-copy** — DONE `feature/issue-603`~~ ✓
6. ~~**#591/#592 PDF scroll→grid/inspector sync** — DONE `feature/issue-591` (flag OFF)~~ ✓
7. ~~**#616 hide icon-grid panel toggle** — DONE `feature/issue-616`~~ ✓

## Feature Branches Awaiting Review

| Branch | Issue | What |
|---|---|---|
| `feature/issue-603` | #603 | Ingest-mode badges (arrow.up.right.square on LINK docs) + delete copy |
| `feature/issue-591` | #591/#592 | PDF scroll→grid sync (NSScrollView observer, flag OFF by default) |
| `feature/issue-616` | #616 | Hide document grid toggle (⌘⇧G, @SceneStorage, per-window) |

## Needs Daniel On Device

- **Batch A verify-then-close sweep** — 30 min with app running:
  - #598 drops route to cursor target
  - #599 pinch-zoom + TIFF 1:1
  - #607 folder reorder
  - #610 Finder folder drop
  - #612 folder drag-out
  - #614 sidebar section header weight
  - #609 Run Workflow button
- **#619/#605** stay open — tail `log stream --predicate 'eventMessage CONTAINS "⏱"'`
- **#556 settings tab layout** — screenshot if still crammed
- **#595 PDF one-page + swipe** — Daniel's call on architecture
- **#520 Sparkle** — needs release-signing cert
- **#590 PDF hover loupe** — probably 0.0.3

## Next Session — Start Here

1. **BLOCK.md is active** — no autonomous work until Daniel merges + clears it.
2. When Daniel merges branches: delete BLOCK.md and run on-device sweep.
3. After sweep closes Batch A: run `/milestone-check` — 0.0.2 may be shippable.
4. Do NOT start 0.0.3 until Daniel approves 0.0.2.

## Parallel Workflow

0.0.3 (Wire: Search v1) queued at `~/code/fichero-0.0.3` — on hold until 0.0.2 approved.

---

*Last updated: 2026-04-20* — All autonomous items done. 3 branches for review. BLOCK.md active.
