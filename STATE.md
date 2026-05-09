# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — pushed `52af797b` (37 commits ahead since 2026-05-01).
Catalogue pipeline now per-page end-to-end (Phase E multi-output + Phase
C/D cleanup tools); inspector V2 has the Finder Get Info shape Daniel
asked for; Debug iteration loop down to ~5s thanks to Embed-skip on
Debug. Apple Intelligence runs locally via on-device Foundation Models.

**Goal:** Daniel runs the new Catalogue pipeline on a real folder and
confirms per-file artifacts land + KG inspector reads well, then we
move to release packaging (#658–#660).

## Open Issues (0.0.2 milestone)

**Release pipeline (Daniel-blocked):**
| # | Title | Status |
|---|---|---|
| #658 | Set up fichero-releases GitHub repo | Needs Daniel to create repo |
| #659 | Build, sign, notarize 0.0.2 DMG | Blocked on #658 + Apple notarytool creds |
| #660 | Dry-run install 0.0.2 on Daniel's machine | Blocked on #659 |
| #661 | Add Fichero download page to tubb.ca | Content writing |
| #662 | Update tubb.ca/fichero with release notes | Content writing |

**Engineering — open or deferred:**
| # | Title | Status |
|---|---|---|
| #178/#803 | Phase C: page_cleanup tool | ✅ Shipped 2026-05-04 |
| #179/#804 | Phase D: folder_cleanup tool | ✅ Shipped 2026-05-04 |
| #180/#805 | Phase E: multi-output catalogue | ✅ Shipped 2026-05-04 |
| #806 | Duplicate Apple Intelligence in model picker | ✅ Closed (dedup at startup) |
| #807 | Phantom SourceKit "Self has no member" errors | ✅ Closed (3 real lint fixes) |
| #720 | Catalogue (composable) doesn't emit combined artifact | Resolved by Phase E (multi-output) |
| #721 | Inspector shows parent's container artifacts on child page | Inspector V2 ships per-doc strict scope |
| #702 | Drag-drop folder onto PDF row | Validation matrix, not started |
| #598 | Sidebar drop routes to selected row, not cursor target | Pending |

## In Progress

- Inspector V2 Phase 2 (#156): RTF-editable panels ✓, delete ✓, AI
  display attributes (deferred), per-type artifact payloads (deferred).

## Blocked

Nothing right now. Daniel needs to test the new pipeline end to end on
a real folder before the release packaging path opens up.

## In Progress

- **LLM-stack overhaul (#872 master plan)** — 15 issues closed overnight; archive in HISTORY.md.
- Inspector V2 Phase 2 (#156) — RTF panels shipped; AI display attributes + payload types still pending.

## Blocked

- #854 Apple Intelligence proactive token budgeting — waiting on macOS SDK 26.4 release.

**Decisions logged (Daniel approved):**
- Theme C: stay on fm-bridge as canonical Apple integration.
- Theme A: do the LLMProvider Protocol refactor — long-hall worth it.

## Branch reconciliation — DECISION (2026-05-08)

**Stay on 0.0.2. Re-implement the 0.0.3 features here.** Merging the
two branches surfaced 16 real conflicts (mostly across the directory
rename + file-splitting refactors that happened independently).
Re-implementing the 10 features from 0.0.3 directly on 0.0.2's path
structure is cleaner: each feature is a clean commit, every test
passes deterministically, no merge metadata noise.

The 0.0.3 worktree (`~/code/fichero-0.0.3`) stays as a frozen reference —
read its commits to see the implementation that needs porting. The
0.0.3 *branch* is effectively orphaned; its commits get re-derived on
0.0.2.

### Features to port from 0.0.3 (reference commits)

Read the diff at each commit in `~/code/fichero-0.0.3` then re-implement
on 0.0.2 paths. Path mapping: `fichero-swiftui/` → `fichero/`,
`fichero-api/` → `fichero-engine/` (Python isn't touched in any of
these — they're all Swift UI).

| Issue | 0.0.3 commit | What |
|---|---|---|
| #517 | `e80f00c6` | Library list/table/map re-enable + Finder-style search criteria strip |
| #518/#519 | `57981ec6` | Processing poll + Artifacts column |
| — | `4c51202e` | Resolve pre-existing OpenAPI schema migration build errors |
| #326 | `15786e4a` | Wire left/right pane navigation for list/table/map modes |
| #618 | `8c4cce4c` | Flatten sidebar row indentation to NNW-style near-flush |
| #602 | `a6b27e4e` | Sidebar sibling reorder via `.onMove` + shadow @State |
| #617 | `3487786b` | Per-column NNW-style toolbars (sidebar/content/inspector strips) |
| #593 | `e6c30600` | Swipe-to-navigate sibling documents in preview pane |
| #675 | `9af7994c` | `convertToSendable` preserves Date/URL/NSNumber types |
| #354 | `eaf1f99d` | Bound inspector close button hit area to its icon |

### Audit (2026-05-08): most are already on 0.0.2

After 0.0.3 shipped (Apr 23), 0.0.2 had ~2 weeks of work that
independently re-implemented most of these features under the new path
structure. Verified by grep on 0.0.2's tree:

| Issue | 0.0.3 commit | Status on 0.0.2 |
|---|---|---|
| #354 | `eaf1f99d` | **N/A** — bug doesn't apply; 0.0.2 uses standard SwiftUI ToolbarItem, not the InspectorColumnHeader HStack the fix targeted |
| #675 | `9af7994c` | **N/A** — `convertToSendable` lives in different file structure on 0.0.2; not the same code path |
| #602 | `a6b27e4e` | **✅ Done** — `.onMove` wired in `SidebarItemRow.swift:545` and `SidebarView+ViewComponents.swift:271`; MEMORY.md `feedback_onmove_shadow_state.md` documents the pattern |
| #326 | `15786e4a` | **✅ Done** — `cyclePaneFocus` in `ContentView+Actions.swift:15`; navigation wires through `onRequestPreviousPaneFocus` / `onRequestNextPaneFocus` |
| #617 | `3487786b` | **✅ Done** — `MiniToolbar.swift` exists in `Views/Toolbars/`; per-column toolbar pattern in place |
| #618 | `8c4cce4c` | **TBD** — verify sidebar indentation matches NNW-style |
| — | `4c51202e` | **TBD** — backend schema build errors; check if they apply to current llm.py / OpenAPI shape |

### Truly missing — port these (in suggested order)

| Issue | 0.0.3 commit | What | Notes |
|---|---|---|---|
| #519 | `57981ec6` | Artifacts column on document list | Half of the processing-poll / Artifacts commit; the column is the visible piece |
| #518 | `57981ec6` | Processing-status poll | Background poller updates document status; pairs with #519 |
| #593 | `e6c30600` | Swipe-to-navigate sibling docs in preview | Trackpad swipe → next/prev sibling; MEMORY.md `feedback_nsswipe_gesture_missing.md` notes NSSwipeGestureRecognizer doesn't exist on Swift macOS — must use `NSEvent.addLocalMonitorForEvents(matching: .swipe)` |
| #517 | `e80f00c6` | Library list/table/map view modes wired + Finder-style search criteria strip | **Highest-value piece for Search v1.** SearchCriteriaStrip.swift is the one new file. List/table view modes have skeleton on 0.0.2 (`ViewDisplayMode.table` enum case exists) but may need to be actually wired to render. |

### Then for Search v1 (#481)

After the criteria strip lands, add the actual `.searchable(text: $queryText, prompt: ...)` to SearchView so users can type queries (this is the original "input not wired" gap). 30-60min, all in `fichero/fichero/Views/Search/SearchView.swift`.

## Next Session — Start Here (2026-05-09 evening hand-off)

**Latest commit on 0.0.2: `af1f30ff`** (clear-filter escape, lozenge
middle-truncation, single-click no longer hijacks filter). xcodebuild
verified clean on every commit pushed today.

### Visual bugs flagged from morning test (priority for next pass)

1. **Sidebar window background too dark** — visibly different shade
   from the rest of the window. Needs lighter material to match the
   content area. (Screenshot 2026-05-09 8:40 AM.)
2. **Margin between sidebar and toolbar** — no visible separation
   between sidebar's top edge and the window toolbar; needs a touch of
   padding or a divider.
3. **Toolbar background is off** (Daniel's last 2026-05-09 message)
   — full visual treatment audit across sidebar / window toolbar /
   pane mini-toolbars so they feel coherent.

### Functional queue (started, not finished)

4. **Filter button → top-right TOOLBAR for all library views** (icon /
   list / table / map), not just an overlay on list. Already removed
   the list-only overlay in `LibraryView+DisplayModes.swift`; needs a
   `ToolbarItem(placement: .primaryAction)` wired in the parent that
   calls `entityFilterMenu`. (Half-shipped.)
5. **Per-folder view-mode persistence verification.** Plumbing exists
   (`folderViewDisplayModesJSON` @SceneStorage on ContentView,
   `displayMode(for:)`/`saveDisplayMode(_:for:)` in
   `ContentView+Persistence.swift`). Daniel reports view mode isn't
   sticking per folder — either save isn't called on folder change or
   load isn't being applied.
6. **Sidebar layout for macOS Tahoe** — needs a screenshot to fix.

### Don't break

- Single click on a MailStyleRow selects only — do NOT re-add tag-tap
  `onTapGesture` to badges. Daniel hit a stuck-filter bug.
- "Clear Filter" button must be visible whenever `!searchText.isEmpty` —
  it's the user's only escape from a bad filter state.
- `Table` builder caps at 10 columns — don't add an 11th without
  computed-property column-groups refactor.
- `WindowState.libraryId` is non-optional UUID — don't `if let` it.
- Run `xcodebuild` before every Swift push, not just `swiftlint`.

### Architectural follow-ups (for 0.0.3+)

- **#874** User-extensible entity types — registry-driven backend +
  frontend re-architecture. The 6 types are baked into the Pydantic
  `_Extraction` class AND into 6+ frontend call sites. 0.0.4 scope.
- **#868** LLMProvider Protocol refactor — foundation laid. 0.0.3.
- **#481/#482/#483** — Search v1 / v2 / v3 release gates. v1 is in this
  0.0.2; v2 + v3 are 0.0.4 / 0.0.5.

### Read for context

- `docs/architecture/api/development_standards.md` — 6 LLM-stack contracts
- `MEMORY.md` 2026-05-07/08/09 — durable patterns
- `HISTORY.md` — session-by-session log
- GitHub `#874` — user-extensible entity types brief

---

## Earlier next-session entry (kept for continuity)

**Latest commit on 0.0.2: `3d50df04`** (10 integration tests for the LLM
fallback chain, mocked at the network boundary, no internet calls).

### 0.0.2 milestone state

Open: 9 (was 16). Closed: 265+. Ratio 96%.

The remaining 9 are: #659–#665 (release packaging, all Daniel-blocked),
#821 (Apple Intelligence Tool calls — bigger feature, deferrable), #868
+ #872 + #873 (LLM-stack follow-ups — all doable now), #854 moved to
0.0.3 (genuinely blocked on macOS SDK 26.4).

### Highest-value next thing: #868 LLMProvider Protocol refactor

**Read first:** the implementation brief I wrote inside the issue
(GitHub comment dated 2026-05-07). It has the exact 5-commit sequence
+ file paths + risk analysis. Don't re-derive — execute.

**Quick orientation:** the foundation is already in `llm.py`:
- `AppleUnavailableError` hierarchy (~line 145)
- `_compute_timeout(config, kind, *, schema_chars=None)` (~line 1308)
- `collect_usage()` + `_record_usage()` (~line 70)
- Reasoning routing in `get_langchain_model` (~line 1850)

The refactor wraps these into provider classes; dispatchers replace the
in-line `if config.provider == "apple": ... else: ...` branches.

### Other paths

- **#873 next slice:** the 10 fallback-chain tests are scoped piece 1.
  Pieces 2/3 would be (a) a workflow-execution-runner test with mocked
  tools, (b) an end-to-end test driving the FastAPI route. Both need
  fixture-infra design choices first.
- **Live verification still pending:** restart backend on a recent commit
  and re-run Catalogue (Mixed) on Legal Case to confirm the Spanish
  locale fix works in production.
- **Cellphone-aware rule for autonomous loop:** mock all LLM calls in
  tests; never write a test that hits real provider APIs without an env
  flag (`FICHERO_INTEGRATION=1`) and `pytest.skipif` guard.

### Don't break

- AppleUnavailableError fallback works because `chat_with_fallback` /
  `chat_structured_with_fallback` catch the base class. Don't catch
  `GuardrailViolationError` specifically anywhere.
- Don't add a fourth timeout formula somewhere. Use `_compute_timeout`.
- Don't `logger.info("LLM usage ...")` directly. Use `_record_usage` so
  the contextvar collector picks it up.
- Don't add a second Apple path. fm-bridge is canonical.

### Read for context

- `docs/architecture/api/development_standards.md` — 6 contracts under
  "LLM Stack Architecture (post-#872)"
- `MEMORY.md` 2026-05-07 entries (7 durable lessons)
- HISTORY.md 2026-05-07 session summary
- GitHub issue #868 comment "Implementation brief — for fresh-context resumption"
2. **If per-file works**: move on to release pipeline #658–#660 (DMG
   build / notarize / dry-run install).
3. **If per-file doesn't land**: check engine.log for
   `page_cleanup(<key>): wrote <key>_clean on N/M descendant docs` —
   N>0 means it's working. If N=0, the records flow lost doc_ids
   again; verify catalogue.json has both `transcribe.texts → aggregate.text`
   AND `files-source.documents → aggregate.documents` (force-reseed
   defaults via Settings if not).
4. Iterate on the inspector via plain Xcode: `BuildProject` (~1.5s) +
   `open .../Fichero.app` (~5s end-to-end). Don't try SwiftUI
   previews of the Inspector — they hit the 30s app-launch timeout
   and the SPM workaround isn't worth the duplication cost.
5. New bugs Daniel files via `/bug` go to milestone 0.0.2.

## Architecture Reminders

- **Engine**: external (`./fichero-engine/scripts/start_backend.sh` or
  briefcase dev) — Debug Embed phase no longer copies the briefcase
  bundle; the Swift app probes `:8765` for 5s and uses whatever's there.
- **Auth**: token at `~/Library/Application Support/Fichero/.api-key`,
  written by `initialize_token()` on every engine start regardless of
  launch path.
- **Test 2 folder**: `7dbba674ae204be9b08dc8df5a00f6fa` (Asprilla,
  15 files); Catalogue workflow id changes per reseed — query
  `/api/workflows/` to find current.
