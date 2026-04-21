# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — tip `ba00d904`. All autonomous code work done and merged. Waiting for Daniel's on-device verification sweep before release.

**Goal:** Daniel runs on-device sweep → closes Batch A issues → cuts 0.0.2 release.

## What's Merged (all on 0.0.2)

1. ✓ #622 icon/list grid column min-width
2. ✓ #594 close-as-skipped (tests skip when fixtures absent)
3. ✓ #619/#605 startup instrumentation (⏱ OSLog breadcrumbs)
4. ✓ #600 .mov drag-drop fix (canLoadObject fallthrough + OSLog)
5. ✓ #603 ingest-mode badges + delete-copy dialog
6. ✓ #591/#592 PDF scroll→grid/inspector sync (flag OFF by default)
7. ✓ #616 hide document grid toggle (⌘⇧G, @SceneStorage, per-window)
8. ✓ #614 sidebar section headers bolder (.foregroundStyle(.primary))

## Next Session — Start Here

1. **Daniel does on-device sweep** (see checklist below).
2. After sweep, close verified issues and run `/milestone-check`.
3. If milestone passes → proceed to #520 (Sparkle, needs cert) and cut release.
4. Do NOT start 0.0.3 until Daniel approves 0.0.2.

## Remaining open issues (all need Daniel on device)

| # | What | Notes |
|---|---|---|
| #598 | Sidebar drops land on selected row not cursor target | Batch A |
| #599 | Image pinch-zoom + TIFF 1:1 broken | Batch A |
| #607 | Folder reorder by drag | Batch A |
| #610 | Finder folder drop flattens children | Batch A |
| #612 | Sidebar folder drag-out broken | Batch A |
| #609 | Run Workflow toolbar button | Batch A |
| #556 | Settings tab layout crammed | Screenshot if still broken |
| #619/#605 | Startup slow — tail ⏱ logs | `log stream --predicate 'eventMessage CONTAINS "⏱"'` |
| #595 | PDF one-page + swipe | Daniel's architecture call |
| #590 | PDF hover loupe | Likely 0.0.3 |
| #520 | Sparkle auto-update | Needs release-signing cert |

---

*Last updated: 2026-04-21* — All autonomous code merged. On-device sweep is the gate.
