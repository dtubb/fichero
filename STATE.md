# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — pushed and clean.

**Active worktrees:**
- `~/code/fichero-0.0.2` — bug fixes, Daniel testing
- `~/code/fichero-0.0.3` — Wire: Search v1 (Claude loop, branch `0.0.3`)

**Status:** 0.0.2 bug sprint completed this session — 20+ bugs closed. App launches, drag/drop works, selection works, focus rings update, PDF thumbnails render locally. Ready for Daniel to verify.

## In Progress

Nothing active.

## Known Deferred

- **#548 FocusedValue warning** — "update tried to update multiple times per frame" on launch. Needs focusedSceneValue usage review (probably from multiple `@Published` state changes in same frame during `onAppear`). Cosmetic warning, not a crash.
- **#554b PDF preview zoom toolbar** — needs a PDFKit-based preview view (currently QLPreviewView provides no zoom controls). Deferred to 0.0.3+.
- **2.5s startup gap** between library restore and backend start is SwiftUI first-layout + `@StateObject` chain init. Not library restoration. Optimization would need view hierarchy simplification.

## Test Health

**190+ passing, 13 pre-existing failures** (all from missing `fichero-api/scripts/export_api_schemas.py` which was never written + `endpoints.json` not discoverable at Xcode test runtime).

## Next Session — Start Here

1. **Daniel: relaunch and verify** — focus rings, drag-drop visibility, workflow feedback, settings layout, PDF thumbnails, subfolder selection, Reveal in Finder context menu.
2. **#520 Sparkle** — still needs manual verification (Check for Updates menu item).
3. **If all clean:** `/release 0.0.2`, then rebase 0.0.3 onto it.
4. **In `~/code/fichero-0.0.3`:** resume Wire: Search v1 (`/session-start-auto`).

## Parallel Workflow

Daniel tests N → Claude builds N+1 in a separate worktree.
Gate: Claude never merges without Daniel's `/release N`.

---
*Last updated: 2026-04-16* — 20+ bugs closed this evening (#538-#558); #548/#554b deferred; #520 Sparkle + release remain.
