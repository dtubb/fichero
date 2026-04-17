# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — pushed, clean (through `e13d0a45`).

**Active worktrees:**
- `~/code/fichero-0.0.2` — bug fixes + sidebar robustness overhaul, Daniel testing
- `~/code/fichero-0.0.3` — Wire: Search v1 (Claude loop, branch `0.0.3`)

**Status:** Sidebar robustness plan drafted and partly executed on `0.0.2` (Daniel corrected mid-session: sidebar is a 0.0.2 ship blocker, not 0.0.3+ work, because 0.0.1 is private and 0.0.2 is the first public release). Full plan at `agent-work/proposals/sidebar-robustness-plan.md` — 12 steps; 4.5 shipped this session.

## This Session (2026-04-17, session 3)

8 commits pushed to 0.0.2:
1. `2ac122e6` chore(agents): three-leg Swift check non-negotiable
2. `99f84918` fix: PDF pinch-zoom snap-back (#588) + autoScales observer + Coordinator test suite
3. `639b8a94` fix: JPG picker case-insensitive (sidebar plan Step 1)
4. `d7210880` refactor: extractActualId free function + cross-view drag test (Step 2)
5. `a41fabb2` feat: sortOrder on Swift Document model (#572, Step 3)
6. `dc1573e3` refactor: drop-target modifiers extracted per shape (#585, Step 6)
7. `e13d0a45` feat: double-click on sidebar label starts rename (Step 8 partial)
8. Plus the plan doc itself under `agent-work/proposals/`

**Session-end agents still addressable (persistent):**
- `bug-intake` — filed #590 (PDF hover magnifier missing), #591 (PDF scrollbar doesn't update grid), #592 (PDF scroll doesn't update inspector)
- `feature-future-intake` — filed #593 (Preview-style swipe navigation, 0.0.3)

## In Progress

Nothing actively coding.

## Test Health

**Swift Testing suite:** 53 sidebar-adjacent tests all green post-refactor. PDFPageViewZoomTests (3 new, #588), IDPrefixStrippingTests (5 total, +1 new for bare-UUID cross-view drag), SidebarItemFactoryTests (2 new for sortOrder propagation).

**Pre-existing failures** (unchanged by this session, orthogonal to sidebar):
- 13 OpenAPI contract tests fail because `endpoints.json` / contract fixtures aren't generated. Fix: run `python fichero-api/scripts/export_openapi_schema.py` and `export_api_schemas.py`.
- 1 UI launch test (`FicheroUITestsLaunchTests/testLaunch`) fails with `NSInternalInconsistencyException`.

## Next Session — Start Here

Sidebar plan has 7.5 steps left. Recommended next moves:

1. **Step 8 completion (keyboard rename)** — Return key on selected row triggers rename. The partial work in this session shipped double-click. Approach: add a hidden `Button` with `.keyboardShortcut(.return, modifiers: [])` scoped to the sidebar List that calls `renameState.startRename` on the selected item. Double-click already works.

2. **Step 9 (cross-section folder drops)** — Sidebar drops of saved searches / chats / workflows onto folder rows of the matching section. Backend routes already exist (see MEMORY.md: `feedback_backend_folder_path_already_there.md`): use existing `PUT /search/saved/{id}`, `PATCH /chat/conversations/{id}`, `PATCH /workflows/{id}` with `folder_path` in body. Swift side: in `SidebarItemRow+DropHandlers.swift`, detect ID prefix (`search:`, `chat:`, `workflow:`) and dispatch to the right service call. Blocker: `folderDropTarget` view modifier (Step 6 done) already centralises the drop chain — Step 9 just extends `handleDropIntoFolder` with type-dispatched routing.

3. **Step 7 (DropDelegate between-row drops, #580)** — HIGH RISK. The `.onInsert` crash on macOS 14+ is documented; DropDelegate is the suggested replacement but may hit the same `HomogeneousCollection` bug. **Prototype first in a throwaway project before committing**. Plan's Risk 1 is explicit.

4. **Step 4 (wire POST /documents/reorder)** — depends on Step 7 for real position data. Without Step 7, the reorder call would just re-persist the server-determined order, not the user's drop position.

5. **Step 11 partial (test coverage sprint, #583)** — can start NOW: items 1, 2, 3, 5, 6, 10 from the plan are unit-testable without other Step dependencies. Item 6 (sortOrder sorting in buildLibraryHierarchy) is the most valuable because it changes observable sidebar order once Step 4 lands.

6. **Step 10 (accessibility pass, #584)** — infra, any time.

7. **Step 12 (grid→sidebar UX polish)** — depends on Step 6 (done). Quick wins: success-toast on cross-view drop, visual feedback.

**Things Daniel still needs to verify** (from earlier sessions):
- `#588` PDF pinch-zoom (shipped this session, `99f84918`) — trackpad pinch should now stick. Relaunch Fichero and try it.
- `#556` settings `.formStyle(.grouped)` — awaiting retest
- `#571` sidebar drop highlight — awaiting retest

**Known 0.0.2 bugs still open (not yet touched this session):**
- `#520` Sparkle auto-update integration
- `#589` kreuzberg cache cwd pollution (band-aid `.gitignore` shipped prior session; proper fix: explicit `cache_dir` in `fichero-api/src/fichero/loaders/{pdf_loader.py:156, document_loader.py:128}`)
- `#590` PDF hover magnifier/loupe missing (filed this session)
- `#591` PDF scrollbar drag doesn't update grid selection (filed this session)
- `#592` PDF scroll doesn't update inspector (filed this session)

## Parallel Workflow

Daniel tests N → Claude builds N+1 in a separate worktree. 0.0.2 is Daniel's current test target AND Claude's active branch (sidebar pushed the "one ahead" boundary — sidebar polish required for public release). 0.0.3 (Wire: Search v1) waits.

Gate: Claude never merges to `main` without Daniel's `/release N`.

---

*Last updated: 2026-04-17 (session 3)* — Sidebar robustness plan drafted; Steps 1, 2, 3, 6, 8-partial shipped. PDF pinch-zoom (#588) fixed. Three PDF bugs filed (#590/591/592), one feature request filed (#593). Routing pattern established: `bug:` / `future:` prefixes forward to persistent intake agents (`bug-intake`, `feature-future-intake`) that remain addressable across session boundaries via SendMessage.
