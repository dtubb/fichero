# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — pushed, clean.

**Active worktrees:**
- `~/code/fichero-0.0.2` — bug fixes, Daniel testing
- `~/code/fichero-0.0.3` — Wire: Search v1 (Claude loop, branch `0.0.3`)

**Status:** 9 bugs closed this session. 0.0.2 open items narrowed to 3: two awaiting Daniel's verification retest, one task (#520 Sparkle), one new feature ask (#588 PDFView pinch).

## In Progress

Nothing actively coding. Ready for Daniel's test cycle on last shipped commit `413b6614` (PDF preview↔grid sync, folder drop fix, settings `.formStyle(.grouped)`).

## Test Health

**Swift Testing suite:** 25+ passing (SidebarItemBuilder, DocumentNavigation, PDFThumbnailRendering, DragDropModel). No regressions introduced this session.

**Python backend tests:** 190+ passing, 13 pre-existing infra failures (missing `endpoints.json`/`export_api_schemas.py` — separate from 0.0.2 work).

## Next Session — Start Here

1. **Daniel: end-to-end smoke test of 413b6614.** Drop folder from Finder → folder should appear as a row with its children inside. Click a PDF → grid shows pages. Scroll the preview → grid selection follows. If any of these fail, file a focused bug.
2. **#556 verify** — settings layout fix (`.formStyle(.grouped)`) still awaiting Daniel's screenshot retest.
3. **#588 PDF pinch-zoom** — quick audit: grep `.gesture`/`.simultaneousGesture`/`MagnificationGesture` in ancestors of `PDFPageView`; test trackpad pinch. If blocked, add `.highPriorityGesture(MagnificationGesture())` that proxies to PDFKit's zoom.
4. **#580 between-row drops (0.0.6)** — when Daniel confirms 0.0.2 is ready to ship, start on `DropDelegate` + `CGPoint` implementation. Dormant helpers (`handleInsertBetweenChildren`, `handleLibraryRootInsert`) are pre-wired in the code for reuse.
5. **#520 Sparkle** — last 0.0.2 task; needs SDK wire-up, appcast signing, update-check UI.

## Parallel Workflow

Daniel tests N → Claude builds N+1 in a separate worktree.
Gate: Claude never merges without Daniel's `/release N`.

---
*Last updated: 2026-04-17* — PDF as first-class container now fully wired: data model (#568), sidebar (#570/#581), single-click drill-in (#577), interactive preview (#578), preview↔grid sync (#586). Folder drops preserve URLs (#587). Awaiting Daniel's verification pass before cutting 0.0.2.
