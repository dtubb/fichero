# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — tip `596b3aee`. Bug batch fixed and pushed. Waiting for Daniel's on-device sweep before release.

**Goal:** Daniel runs on-device sweep → closes verified issues → cuts 0.0.2 release.

## What's Merged (all on 0.0.2)

### Previous session
1. ✓ #622 icon/list grid column min-width
2. ✓ #594 close-as-skipped (tests skip when fixtures absent)
3. ✓ #619/#605 startup instrumentation (⏱ OSLog breadcrumbs)
4. ✓ #600 .mov drag-drop fix (canLoadObject fallthrough + OSLog)
5. ✓ #603 ingest-mode badges + delete-copy dialog
6. ✓ #591/#592 PDF scroll→grid/inspector sync (flag OFF by default)
7. ✓ #616 hide document grid toggle (⌘⇧G, @SceneStorage, per-window)
8. ✓ #614 sidebar section headers bolder (.foregroundStyle(.primary))

### This session (2026-04-21)
9. ✓ #623 sidebar drag-out HTML artifact (ownProcess visibility) — 6ef516cf
10. ✓ #624 PIL JPEG crash — sips fallback — 6ef516cf
11. ✓ #626 drag-drop stores temp path (.link → .copy) — 6ef516cf
12. ✓ #609 toolbar Run Workflow: pre-capture selection + navigate to Activity — 8122a6e2
13. ✓ #610 Finder folder drop flattens children — 14146f8e (backend, verified working, closed)
14. ✓ #625 JSON/text file thumbnails via PIL ImageDraw — 596b3aee
15. ✓ Activity sidebar: Mail-style two-column layout (runs list + detail) — prior commits
16. ✓ Artifact mid-run refresh via fileCompletedCount observable — prior commits
17. ✓ SystemicErrorDetected pickle compat (optional __init__ args) — prior commits

## Next Session — Start Here

1. **Daniel does on-device sweep** (see checklist below).
2. After sweep, close verified issues and run `/milestone-check`.
3. If milestone passes → proceed to #520 (Sparkle, needs cert) and cut release.
4. Do NOT start 0.0.3 until Daniel approves 0.0.2.

## Remaining open issues (need Daniel on device or a direction call)

| # | What | Notes |
|---|---|---|
| #598 | Sidebar drops land on selected row not cursor target | Fix shipped in 31b6c53a — on-device verify needed |
| #595 | PDF one-page + swipe | Daniel's architecture call (3 options in issue comments) |
| #619/#605 | Startup slow — tail ⏱ logs | `log stream --predicate 'eventMessage CONTAINS "⏱"'` |
| #520 | Sparkle auto-update | Needs Daniel to set SPARKLE_FEED_URL + SPARKLE_PUBLIC_ED_KEY in xcconfig |
| #607 | Folder reorder by drag | Deprioritized by Daniel ("sort of works, leave it") |

---

*Last updated: 2026-04-21* — Bug batch complete. On-device sweep is the gate.
