# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — pushed, clean (through `c025e685`).

**Active worktrees:**
- `~/code/fichero-0.0.2` — sidebar robustness + bug-fix sprint, Daniel testing
- `~/code/fichero-0.0.3` — Wire: Search v1 (on hold)

**Status:** Session 4 (2026-04-17) continued from session 3 and added another 10+ commits. Drop-handling regressions fixed via targeted revert + rewrite. `.mov` drop bug fixed. Image pinch re-fixed with a gesture-state gate to avoid the #599 race. Accessibility pass landed. 9 Dependabot alerts resolved.

## Session 4 — New commits since `39cf4504`

| SHA | What |
|---|---|
| `97863771` | revert `76ba6785` drop highlight (diagnostic for #598) |
| `8eeabee3` | revert `fc01d393` image pinch v1 (caused #599) |
| `044add35` | **fix**: accept all URL-producing drag sources, not just `.fileURL` (#600, .mov fix) |
| `1aa58bb9` | **chore(deps)**: `npm audit fix` in site/ — 9 Dependabot alerts resolved (#601 closed) |
| `170150e0` | **fix**: image pinch sticks via gesture-state gate (#596, 2nd attempt) |
| `1c2acc9c` | **feat**: VoiceOver labels, hints, expansion on sidebar rows (#584, Step 10) |
| `c025e685` | **feat**: VoiceOver labels on library headers (#584, Step 10 rounded out) |

## All session commits to date (sessions 3 + 4)

25 commits on `0.0.2` covering: AGENTS.md hardening, #588 PDF pinch, #596 image pinch (with v1/v2 retry), JPG picker (#600), sortOrder (#572), drop modifier refactor+revert, double-click rename (Step 8), cross-section drops (Step 9), sortOrder sort (Step 11 partial), Finder drop highlight+revert, .mov fix, Dependabot cleanup, accessibility pass (Step 10).

## Issues status

**Closed this session:** #588, #596 (×2 — reopened after #599), #601.

**Open and awaiting Daniel's device-verification:**
- `#598` sidebar drag-drop routing — reverted suspect commit; if symptom persists, 3 diagnostic hypotheses logged on the issue
- `#599` image pinch regression from v1 fix — reverted; v2 fix lands in `170150e0` which gates sync during gesture
- `#600` .mov drag-drop — UTI-agnostic filter in `044add35`; verify by dragging a .mov from Finder

**Open and still needing work:**
- `#520` Sparkle auto-update
- `#580` DropDelegate between-row drops (plan Step 7, HIGH RISK — needs throwaway prototype)
- `#583` sidebar test coverage remainder (5 tests left)
- `#585` sidebar polish follow-ups (drop highlight polish after #598 fix lands)
- `#589` kreuzberg cache cwd
- `#590` PDF hover magnifier
- `#591` / `#592` PDF scroll→grid/inspector (may be superseded by #595)
- `#594` contract test infra
- `#595` PDF swipe navigation (awaits Daniel's design go-ahead)
- `#597` link/copy/sync corner badge

## Test Health

**Swift Testing suite:** All sidebar-adjacent tests green post-revert. 50+ tests touching drop routing + `SidebarItem.folderKind` + `SidebarItemKind` + `childOrder` sort + `IDPrefixStripping` + `DropURLValidation`.

## Sidebar plan status

- ✅ Step 1 — JPG picker
- ✅ Step 2 — extractActualId
- ✅ Step 3 — sortOrder field
- ✅ Step 5 — (backend routes already existed — confirmed, no new code)
- ✅ Step 6 — Reverted after bug discovered (see `MEMORY.md` feedback_state_binding_through_value_copy)
- ⚠️ Step 8 — Partial: double-click rename ✅; F2/Return keyboard deferred
- ✅ Step 9 — Cross-section folder drops
- ✅ Step 10 — Accessibility pass (rows + headers)
- ⚠️ Step 11 — Partial: sortOrder sort tests ✅; 5 more tests pending
- ⛔ Step 7 — Not started (HIGH RISK, needs throwaway prototype)
- ⛔ Step 4 — Not started (blocks on Step 7 for real position data)
- ⛔ Step 12 — Not started (grid→sidebar polish)

## Next Session — Start Here

1. **Daniel: launch + verify** #598, #599, #600 are resolved per the commits above.
2. **If #598 persists after the `76ba6785` revert**, the prime suspect is incorrect. Add the diagnostic log one-liner from the issue body and capture `log stream --subsystem com.fichero.app --predicate 'category == "SidebarRow"'` during a broken drop, then re-investigate.
3. **Step 7 (DropDelegate between-row drops, #580)** — the remaining high-value UX gap. Plan calls for prototyping in a throwaway project first to rule out the `HomogeneousCollection` crash before committing to Fichero.
4. **Step 8 (F2/Return keyboard rename)** — hidden Button with `.keyboardShortcut(.return, modifiers: [])` scoped to the selected row OR `@FocusedValue` pattern per the architecture docs.
5. **Step 11 remainder** — 5 more unit tests (handleProvidersDrop URL filter, parentFolderItem resolution, handleDropBesideItem sibling semantics, RenameStateManager blur-cancel, isDescendant cross-tree).

## Persistent Agents (still addressable via SendMessage)

- `bug-intake` — filed #590, #591, #592, #596, #597, #601 this session
- `feature-future-intake` — filed #593, #595 this session

Either can resume in next session without re-briefing. Use `bug:` / `future:` prefixes to route.

## Parallel Workflow

0.0.2 is the first public release (0.0.1 is private). Sidebar polish + drop-handling correctness is a 0.0.2 blocker. 0.0.3 (Wire: Search v1) waits. Gate: Claude never merges to `main` without Daniel's `/release N`.

---

*Last updated: 2026-04-17 (session 4, final)* — Session 3 + 4 combined: 25 commits on 0.0.2. Sidebar plan core shipped, accessibility pass complete. Three open regressions awaiting Daniel's device-verification (#598, #599, #600). Step 7 + Step 8 + Step 11 remainder are the remaining high-value targets. Dependabot cleared (#601 closed, 9 alerts resolved via `npm audit fix` on site/).
