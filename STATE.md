# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — tip `46c3e7fb`. 16 open issues remain; #594 closed, #600 fixed (canLoadObject fallthrough + OSLog), #619/#605 instrumented (open pending Daniel log analysis).

**Goal:** close 0.0.2 and ship. Plan below batches by effort and tags each item `[autonomous]` (loop-safe) or `[needs-daniel]` (on-device / judgment / credentials).

## How this file drives an autonomous loop

A `/loop` agent starting fresh should:
1. Read "Autonomous execution order" below.
2. Work items top-down, committing after each fix.
3. When the next item is `[needs-daniel]` OR all `[autonomous]` items are done, write `BLOCK.md` and stop.
4. Never close an issue that requires on-device verification — leave those for Daniel.

All `[autonomous]` items have been scoped so they can ship without opening the running app. Verification is deferred to Daniel's next on-device pass.

## Autonomous execution order

Work these top-to-bottom. Each is one concern, one commit.

1. ~~**#622 icon/list grid column min-width** — DONE `8792074b` on `0.0.2`~~ ✓

2. ~~**#594 close-as-skipped** — CLOSED. Tests skip when fixtures absent (`61afdbe2`). Deeper fix deferred to 0.0.3+.~~ ✓

3. ~~**#619 / #605 startup instrumentation** — DONE `4c9d0d32`. ⏱ breadcrumbs at AppState.init, checkBackendHealth, loadLibraryData, SidebarItemBuilder.build, ContentView.onAppear. Issues left open pending Daniel's on-device log analysis.~~ ✓

4. ~~**#600 .mov drag-drop** — DONE `46c3e7fb`. Fixed canLoadObject fallthrough (provider lied about URL support for .mov); added OSLog breadcrumbs throughout. Closed #600. Needs Daniel on-device verify.~~ ✓

5. **#603 ingest-mode badges + delete-copy** `[autonomous]` — path-heuristic approach, no DB schema change. In `SidebarItemRow+Label.swift` (or wherever the Label icon renders), check whether the document's `path` starts with the library package path — if yes, it's COPY/MOVE; otherwise LINK. Overlay `arrow.up.right.square` SF Symbol (bottom-trailing, small) when LINK. Same heuristic in the delete-confirmation dialog: if LINK → "Remove the Fichero reference to X? The original at Y will stay on disk." If non-LINK → keep the current "cannot be undone" copy (good enough for 0.0.2; COPY vs MOVE distinction moves to 0.0.3 when we add the schema field).

6. **#591 / #592 PDF scroll → grid/inspector sync, second attempt** `[autonomous, risky]` — first attempt reverted in `9db9b539`. Try: observe `NSScrollView.scrollViewDidLiveScroll` / `.scrollViewDidEndLiveScroll` notifications (cleaner than `boundsDidChange`), or poll `view.visiblePages.first` every 150ms while `NSEvent.pressedMouseButtons & 1 != 0` (left button down = scrollbar drag in progress). Ship behind a feature flag `pdfScrollGridSync` defaulted OFF so Daniel can opt-in without regressing the unflagged path. If flag is OFF the behavior is identical to current tip.

7. **#616 hide icon-grid list panel** `[autonomous]` — plumb a `@SceneStorage("showDocumentGrid")` bool. Toolbar button in `ContentView.swift` near the sidebar/inspector toggles. Keyboard shortcut ⇧⌘L. When false, the three-column `contentWithOptionalModeRail` collapses to sidebar + preview (skip the middle column entirely). Risk: layout regressions in the various `VSplitView` / `HSplitView` modes. Do this LAST in the autonomous run so if it regresses something, it's easy to revert without losing the earlier fixes.

Stop condition: if step 7 compiles and tests pass, write `BLOCK.md` with a summary of what shipped. If any step fails three consecutive attempts, stop there and write `BLOCK.md` with the error.

## Needs Daniel on device or in judgment

Don't attempt these from a loop. They sit here for Daniel's next on-device session.

- **Batch A — verify-then-close sweep** `[needs-daniel]` — 30 min with the app running:
  - #598 drops route to cursor target (drag X onto Y while Z selected)
  - #599 pinch-zoom + TIFF 1:1 (pinch, click 1:1 on a 300 DPI TIFF)
  - #607 folder reorder (drag folder between siblings at nested levels)
  - #610 Finder folder drop (drag a folder with N files from Finder)
  - #612 folder drag-out (overlaps with #598)
  - #614 section header weight + accent selection (visual compare to SimpleSidebar)
  - **#609 Run Workflow** (preview doc open, no grid selection, trigger menu)
- **#556 settings tab layout** `[needs-daniel]` — already uses `.formStyle(.grouped)` at 680pt. If still crammed on Daniel's screen, file a follow-up with a screenshot rather than stabbing blindly.
- **#595 PDF one-page + swipe rewrite** `[needs-daniel]` — pick-one decision: if #595 lands, #591/#592 become moot. Daniel's call on which architecture 0.0.2 ships with.
- **#520 Sparkle auto-update** `[needs-daniel]` — requires release-signing cert. Do right before cutting the first public release.
- **#590 PDF hover loupe** `[needs-daniel]` — feature parity, probably slips to 0.0.3. Daniel decides.
- **#609 part b — workflow input-kind field** `[needs-daniel]` — schema change; spin out as its own ticket for 0.0.3.

## Blocked / flagged

- **Startup (#619)** — poll-interval tighten didn't help per Daniel. Real bottleneck is downstream of the health check. The autonomous step 3 above ships instrumentation; Daniel reads the output.
- **PDF scroll sync (#591/#592)** — first attempt reverted. Second attempt (step 6) is flag-guarded to avoid regression.

## Next Session — Start Here

1. ~~#600 done~~ ✓ — Next: **#603** (ingest-mode badges, path-heuristic, no schema change).
2. **#619/#605 stay open** — Daniel needs to tail `log stream --predicate 'eventMessage CONTAINS "⏱"'` on device.
3. After #603, continue with **#591/#592** (PDF scroll sync, flag-guarded) and **#616** (hide icon-grid panel toggle).
4. Do NOT write BLOCK.md until all autonomous items (#603, #591/#592, #616) are done or blocked.

## Parallel Workflow

0.0.2 is the first public release gate. 0.0.3 (Wire: Search v1) is queued at `~/code/fichero-0.0.3` and stays on hold until Daniel approves 0.0.2. Semantic search UI is 0.0.3 scope.

---

*Last updated: 2026-04-20 (session)* — 4 autonomous items remaining (#603, #591/#592, #616), 6 needs-Daniel items waiting. Next: #603 (ingest-mode badges).
