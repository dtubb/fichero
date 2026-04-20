# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — tip `ad465e4d`. 20 issues remain on milestone 8.

**Goal:** close 0.0.2 and ship. Plan below batches by effort.

## Plan — 0.0.2 release closeout

### Batch A — Verify-then-close (likely fixed, <30 min total)

On-device verification only. If the behavior looks correct at tip, close with a reference to the commit that shipped the fix. If it's still broken, reopen with fresh repro notes.

- **#598** drops route to cursor target — closure-captured `item` shipped earlier this session (`e1f2cd94` + ancestry). Verify: drag row X onto folder Y while row Z is selected; expect drop on Y, not Z.
- **#599** pinch-zoom regression + TIFF 1:1 — `isUserMagnifying` guard + `pixelsWide / size.width` in place. Verify: open TIFF, pinch (should zoom), click 1:1 (should show native pixels).
- **#607** can't reorder folders — my overlay insertion-line (`e1f2cd94`) covers this. Verify: drag folder between two siblings at any hierarchy level.
- **#610** Finder folder drop flatten — `ingest_folder(create_collection=True)` already creates parent Document. Verify: drag a folder with 5 PDFs from Finder → one new folder row with 5 children.
- **#612** folder drag-out broken — overlaps with #598/#607. Verify together.
- **#614** bolder section headers + accent selection — section labels already `.font(.caption).fontWeight(.bold)`; no custom `listRowBackground`. Verify visually against SimpleSidebar.

### Batch B — Small fixes (30–90 min each)

- **#622** icon/list view column min width too wide — lower `.frame(minWidth:)` or `.navigationSplitViewColumnWidth(min:)` on the middle grid column in `ContentView+ViewBuilders.swift`. Same pattern as #615 (sidebar 250→180). Start at 180 for the grid too.
- **#594** contract/endpoint tests — partial fix (skip when absent) shipped. Decide for 0.0.2: either accept the skip-behavior and close, or write `export_api_schemas.py` + wire a build phase to generate fixtures. Close-as-skipped is acceptable for 0.0.2 release gate.
- **#609** Run Workflow — part (a) shipped in `463c3433` but not yet tested. Verify on device. Part (b) input-kind field moves to 0.0.3 (spin out a separate issue).

### Batch C — Medium effort (2–4 hours each)

- **#603** ingest-mode badges + delete-confirmation copy. Approach without touching DB schema: infer mode from document path. File inside `library.packagePath/files/` = COPY or MOVE; file elsewhere = LINK. Can't distinguish COPY from MOVE without the field, but the most user-important distinction is LINK vs not-LINK (delete-copy message differs most there). Part 1: SF Symbol overlay on doc icon (`arrow.up.right.square` for LINK, nothing for COPY/MOVE). Part 2: branch the delete dialog message by mode.
- **#619 / #605** app startup slow — instrument first, optimize second. Add `⏱` OSLog breadcrumbs in `AppState.init`, `checkBackendHealth` completion, `LibraryManager.loadLibraries`, `SidebarItemBuilder.build`. Tail `/usr/bin/log stream --subsystem com.tubb.Fichero --predicate 'eventMessage CONTAINS "⏱"'` while launching fresh. Bottleneck will jump out. Daniel's "not much faster" after the poll-interval tighten suggests the cost is downstream of the health check.
- **#600** .mov drag-drop — repro needed. Attach OSLog around `handleProvidersDrop`, drag a `.mov` from Finder, check which stage drops it. If all UTIs advertise `public.movie` only (no `public.file-url`), the fallback `loadFileRepresentation(forTypeIdentifier:)` branch should cover it — verify the branch actually fires.

### Batch D — Bigger (defer to 0.0.3 unless small-scoped)

- **#591 / #592** PDF scroll → grid/inspector sync — my first attempt (`008c6eba`) was reverted. Try again: poll `view.visiblePages.first` on a short timer while `NSEvent.pressedMouseButtons != 0` (scrollbar being dragged), stop on mouse-up. Alternative path: `NSScrollView` has `scrollViewDidScroll` delegate-style notifications that may reach us where `boundsDidChange` didn't.
- **#595** PDF one-page-at-a-time + swipe — large rewrite; supersedes #591/#592 by design. If undertaking, the scroll-sync work on #591/#592 becomes moot. Decision point: pick the right one for 0.0.2 and close the other.
- **#616** hide icon-grid list panel — layout plumbing in the three-column split. Risky without tests around the layout modes. Maybe defer to 0.0.3.
- **#520** Sparkle auto-update integration — integration work; needs release-signing cert. Best done right before first public release cut.
- **#590** PDF hover loupe — feature parity with image loupe. Non-trivial PDFKit work; could ship post-0.0.2.
- **#556** settings General tab layout — already uses `.formStyle(.grouped)` at 680pt window width. Verify on device; if still crammed, file a follow-up with screenshots rather than stabbing blindly.

### Execution order next session

1. **Batch A verification pass** (open the app, run through 6 bugs). Close what works.
2. **#622** grid column narrower — 10-line change.
3. **#603** ingest badges + delete copy (path heuristic, no DB change).
4. **#619/#605** instrument + profile startup. Fix whatever shows up.
5. **#600** .mov — repro + fix the likely branch.
6. Decide on **#591/#592 vs #595** — pick one strategy, close the other.
7. **#609 part b**, **#520**, **#590**, **#616** — decide which slip to 0.0.3.

## Blocked / flagged

- **Startup (#619)** — poll-interval tighten didn't help much per Daniel. Root cause is downstream; need profiling before next attempt.
- **PDF scroll sync (#591/#592)** — reverted `008c6eba`. Daniel: "PDF is not ready yet." Need a different observation mechanism or wait for the #595 rewrite.
- **Run Workflow (#609)** — part (a) fix shipped but not yet tested on device.

## Parallel Workflow

0.0.2 is the first public release gate. 0.0.3 (Wire: Search v1) is queued at `~/code/fichero-0.0.3` and stays on hold until Daniel approves 0.0.2. Semantic search UI is 0.0.3 scope (feature flag already on; backend endpoints already land).

---

*Last updated: 2026-04-20 (session-end with closeout plan)* — 20 open issues on 0.0.2. Plan batches them by effort; execution order prioritises verify-then-close to shrink the backlog fast.
