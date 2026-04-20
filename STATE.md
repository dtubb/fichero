# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — pushed clean through `008c6eba`.

**Active worktree:** `~/code/fichero-0.0.2` — 0.0.2 bug sweep in progress. Not released.

## This Session (2026-04-20 bug sprint)

13 commits shipped while Daniel went running:

| SHA | Issue | Summary |
|---|---|---|
| `e983607f` | #620, #621 | Inbox drag gate + first pass at spacer-row padding |
| `c4af068b` | #620 | Removed spacer-rows entirely (they inflated to visible empty rows) |
| `e1f2cd94` | #606, #621 | Overlay-based insertion lines inside row frames + `.moveDisabled` for Inbox |
| `bdfb3900` | #613 | Sidebar Delete uses `confirmationDialog` (more reliable on macOS) |
| `058a3e61` | #611 | `.onMove` dispatcher now handles saved-searches + workflows |
| `494983b1` | #589 | Kreuzberg cache routed to `~/Library/Application Support/com.tubb.fichero/kreuzberg` |
| `c7057c24` | #615 | Sidebar column min 250 → 180 |
| `89800140` | #604 | Grid icon/map zoom cap 3x → 5x |
| `61afdbe2` | #594 | Contract/endpoint tests skip instead of fail when fixtures missing |
| `12866a3c` | #619 | Backend health poll interval 1s → 100ms (back off to 500ms after 1s) |
| `463c3433` | #609 | Run Workflow button enabled when preview doc is open (not just grid selection) |
| `3c3dc0ed` | #608 | "Global" library header row removed |
| `008c6eba` | #591, #592 | PDF grid selection follows scrollbar drag via contentView bounds observer |

## Likely-already-fixed (verify on device)

- #598 drop routes to selected row — doc-closure-captured handler landed in earlier session
- #599 pinch-zoom regression — `isUserMagnifying` guard in place
- #599 TIFF 1:1 — uses `pixelsWide / size.width`
- #610 folder drop flatten — `ingest_folder` creates parent Document
- #614 bolder section headers + accent selection — already matches SimpleSidebar

## Intentionally deferred (risky or substantial)

- #600 `.mov` drag-drop — no obvious filter; need repro
- #603 ingest-mode badges — requires DB schema change (add `ingest_mode` column + Pydantic field + migration)
- #605 app startup slow — needs profiling, not speculation
- #590 PDF hover loupe — new feature, parity with image loupe
- #595 PDF single-page + swipe — large rewrite
- #616 hide grid panel — layout plumbing, risky
- #520 Sparkle auto-update — integration feature
- #609 part b (input-kind field on Workflow) — schema + editor UI

## Test Health

**Swift tests:** clean baseline — contract/endpoint tests now skip missing fixtures instead of failing.
**Python tests:** 1783 pass, 21 skipped. 10 failures are DuckDB lock contention (running backend holds the file lock) — not related to this session's changes.

## Next Session — Start Here

1. **On-device verification sweep** — Daniel to run through the 13 commits:
   - Inbox can't drag (tray.fill `moveDisabled`)
   - Drop-line works at ALL hierarchy levels via overlay strips (top 3pt / bottom 3pt of each row)
   - Context-menu Delete now prompts + removes
   - Saved searches + workflows reorder via `.onMove`
   - Sidebar slides narrower (180pt min)
   - Grid zoom goes to 5x
   - Run Workflow button enabled when preview is open
   - Global row gone
   - PDF scroll updates grid + inspector
   - Backend launch feels snappier

2. **If regressions:** revert individually — every commit is a single bug, small diff.

3. **Then tackle deferred work** — startup profiling (#605), ingest-mode badges (#603) are the two that need schema/perf work.

4. **Semantic search for 0.0.2** — Daniel mentioned this. Search feature is flagged ON (`searchEnabledInternal = true`). Verify end-to-end (search box → results → open doc) still works at tip, file bugs for gaps.

## Parallel Workflow

0.0.2 is the first public release (0.0.1 is private). 0.0.3 (Wire: Search v1) waits. Gate: Claude never merges to `main` without Daniel's `/release N`.

---

*Last updated: 2026-04-20 (Daniel-running sprint)* — 13 commits, sidebar/PDF/backend polish. Nothing released.
