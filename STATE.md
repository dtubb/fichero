# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — pushed, clean (through `76ba6785`).

**Active worktrees:**
- `~/code/fichero-0.0.2` — sidebar robustness + PDF/image polish, Daniel testing
- `~/code/fichero-0.0.3` — Wire: Search v1 (Claude loop, branch `0.0.3`) — on hold while 0.0.2 ships

**Status:** Session 3 (2026-04-17) shipped the sidebar robustness plan's core user-visible scope plus #588 and #596 zoom fixes. 15 commits pushed. Two issues closed. Eight bugs filed during testing. Full plan at `agent-work/proposals/sidebar-robustness-plan.md`.

## This Session (2026-04-17, session 3) — 15 commits

1. `2ac122e6` chore(agents): three-leg Swift check non-negotiable
2. `99f84918` **fix**: PDF pinch-zoom snap-back (#588 closed) + 3 regression tests
3. `639b8a94` **fix**: JPG file picker case-insensitive (sidebar Step 1)
4. `d7210880` refactor: extractActualId free function + cross-view drag test (Step 2)
5. `a41fabb2` **feat**: sortOrder on Swift Document model (#572, Step 3)
6. `dc1573e3` refactor: drop modifiers extracted per shape (Step 6) — **reverted**
7. `e13d0a45` **feat**: double-click label rename (Step 8 partial)
8. `b775019c` chore(session-end) mid-session handoff
9. `42020911` **fix**: revert Step 6 extension (broke Finder drop + highlight)
10. `6d855170` **feat**: sort sidebar by sortOrder first (#572, Step 11 partial, 5 tests)
11. `3e65abf7` **feat**: SidebarItemKind classifier (prep for Step 9, 8 tests)
12. `f1a2a3b0` **feat**: cross-section folder drops in sidebar (Step 9, 7 new tests)
13. `fc01d393` **fix**: image pinch-zoom snap-back (#596 closed)
14. `76ba6785` **feat**: Finder-style solid-fill drop highlight

**Issues filed during testing:**
- `#590` PDF hover magnifier/loupe missing
- `#591` PDF scrollbar drag doesn't update grid selection
- `#592` PDF scroll doesn't update inspector
- `#593` Preview-style swipe navigation (0.0.3)
- `#594` Contract + endpoint validation tests fail (infra)
- `#595` PDF preview: switch to one-page + swipe (fixes #591/#592 by design) — awaiting Daniel's go-ahead
- `#597` Library/sidebar: missing corner badge for link/copy/sync ingest mode

## Test Health

**Swift Testing suite:** 65 sidebar-adjacent tests all green. 15 new this session: 8 `SidebarItemKindTests`, 7 `folderKind` tests, 5 `childOrder` sort-priority tests, 2 sortOrder propagation tests, 1 cross-view drag bare-UUID test, plus PDF zoom (3 via #588) fixture helpers made `fileprivate`.

**Pre-existing failures** (untouched, filed as #594):
- 13 OpenAPI/contract tests — endpoints.json + workflow fixtures not generated
- 1 UI launch test

## Next Session — Start Here

Sidebar plan status: **Steps 1, 2, 3, 5, 6-revert, 8-partial, 9, 11-partial, + drop-highlight polish shipped.** Remaining:

1. **Verify on device** — please launch 0.0.2 and check:
   - Finder drag → sidebar folder now imports (regression fixed in `42020911`)
   - Drop highlight is now the solid-blue Finder-style fill on folder rows (`76ba6785`)
   - Double-click label opens rename (`e13d0a45`)
   - Cross-section drops work: drag a saved search onto a search-folder; drag a workflow onto a workflow-folder (`f1a2a3b0`)
   - JPG import via file picker (`639b8a94`)
   - PDF pinch zoom sticks on release (`99f84918`)
   - Image pinch zoom sticks on release (`fc01d393`)

2. **Step 8 completion (Return/F2 keyboard rename)** — deferred this session. Approach: hidden `Button` with `.keyboardShortcut(.return, modifiers: [])` scoped to the selected row, calling `renameState.startRename`. Needs `@FocusedValue` wiring per architecture docs.

3. **Step 7 (DropDelegate between-row drops, #580)** — **HIGH RISK**. Restores Finder's blue-insertion-line UX. Plan's Risk 1 warns the `.onInsert` crash may also hit `DropDelegate` in the same nesting shape. **Prototype in a throwaway project first** before committing. User shows this is the remaining visible gap vs. Finder (no between-row line + drops land on neighbor).

4. **Step 4 (wire POST /documents/reorder)** — depends on Step 7 for real drop-position data. Without it, the reorder call would just re-persist server-determined order.

5. **Step 10 (accessibility pass, #584)** — infra, any time. VoiceOver labels on every interactive sidebar element.

6. **Step 11 remainder (#583)** — 5 more unit tests (handleProvidersDrop URL filter, parentFolderItem resolution, handleDropBesideItem sibling semantics, RenameStateManager blur-cancel, isDescendant cross-tree).

7. **Step 12 (grid→sidebar polish)** — success toast on drop, visual feedback.

**Other 0.0.2 bugs still open (not yet touched):**
- `#520` Sparkle auto-update integration
- `#589` kreuzberg cache cwd pollution (band-aid shipped; proper fix: explicit `cache_dir` in `fichero-api/src/fichero/loaders/{pdf_loader.py:156, document_loader.py:128}`)
- `#590` PDF hover magnifier (feature-sized work)
- `#591` / `#592` PDF scroll→grid/inspector sync (may be superseded by #595)
- `#594` contract test infra (three root causes documented)
- `#595` PDF swipe navigation (awaiting Daniel's design go-ahead — changes from continuous scroll)
- `#597` link/copy/sync corner badge on thumbnails

## Persistent Agents (still addressable via SendMessage)

- `bug-intake` — 0.0.2 bug filing to correct milestone + labels, referenced SHA in body
- `feature-future-intake` — 0.0.3+ feature filing with milestone triage

Either can resume in next session without re-briefing.

## Parallel Workflow

0.0.2 is the first public release (0.0.1 is private). Sidebar polish is a 0.0.2 blocker. 0.0.3 (Wire: Search v1) waits. Gate: Claude never merges to `main` without Daniel's `/release N`.

---

*Last updated: 2026-04-17 (session 3, final)* — Sidebar plan's core shipped: cross-section drops (Step 9), Finder-style drop highlight, sortOrder propagation and sort, double-click rename, JPG import fix. Two zoom bugs fixed (#588 PDF, #596 image). #596 and #588 closed. Five bugs (#590-594, #597) filed during testing. Step 7 (DropDelegate between-row drops) remains the highest-value outstanding item but also highest-risk — prototype-first recommended.
