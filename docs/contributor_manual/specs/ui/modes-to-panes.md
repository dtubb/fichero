# Modes → Panes — Design Spec (#4705)

> Milestone: modes-to-panes
> Manual: TBD — a short note in the Getting Started section explaining: selecting a
> workflow, chat, research project, schedule or entity changes what the panes SHOW, never
> what the Library pane IS — the Library is always the navigator, every kind of thing opens
> beside it in Source/Preview, Reader or the Inspector, not instead of it.

> Design-led (Testing Constitution). The Fichero creative director owns the intent below
> (paraphrased from the epic's Rulings, decided 2026-09-18); tests enforce it; code makes
> them pass. **Status: DRAFT.** Grounded in a read-only architectural review, session
> scratchpad `REVIEW_modes_to_panes.md` (to be committed under this spec when it lands);
> every code claim below carries that review's file:line citation, abbreviated the same
> way: `Nav` = `Views/Shell/ContentView/ContentView+Navigation.swift`, `Detail` =
> `Views/Shell/ContentView/Layout/ContentView+DetailLayout.swift`, `PaneSpec` =
> `Views/Shell/ContentView/Layout/PaneSpec.swift`, `Plan` = `Views/Shell/PaneContentPlan.swift`,
> `Mods` = `Views/Shell/ContentView/ContentViewModifiers.swift`, `SelH` =
> `Views/Sidebar/Sections/SidebarView+SelectionHandling.swift`. Paths are relative to
> `fichero/fichero/` unless stated otherwise.
>
> Tags: **[OK]** true today · **[BROKEN]** regression, code contradicts the ruling ·
> **[GAP]** intended, never built · **[PROPOSED]** decided here, not yet built (this
> program's default tag, since nothing in the migration has landed).

## Intent (the design)

Everything the sidebar can select — a workflow, chat, a research project, a schedule, an
entity, a claim, the knowledge graph — is a **node**, not a **mode**. Selecting one changes
what the panes show; it never changes what the Library pane IS. Concretely:

- **The Library pane is always the navigator.** It never becomes a workflow canvas, the
  legacy Knowledge Graph browser, a research-project workspace, or any other bespoke
  full-width screen. Selecting a node keeps the Library showing the tree/table it already
  showed; the SELECTED thing's content goes to Source/Preview, Reader, or the Inspector.
- **Each surface renders its own rendition of the selected kind** — a workflow's canvas
  rendition lives in Source/Preview, its run-log rendition lives in the Reader; a chat or
  research selection keeps the Library + Reader + Source panes and takes the Inspector for
  its scope/sources.
- **The Inspector belongs to the focused selection.** It shows tabs only for the kind that
  is actually selected — a workflow's palette/node/runs tabs, a chat's Sources/Plan/
  Knowledge/Compare tabs, a document's normal tabs — never a mix, and never a stale kind
  left over from a previous selection.
- **Panes never collapse by selection.** A workspace's applied pane list (kinds, split,
  order) is the source of truth for what panes exist; selecting a node changes pane
  CONTENT, never removes or adds a pane. (Ties `panes-workspaces.md`'s no-collapse-by-
  selection intent to the mode migration specifically.)

## Current architecture (grounded, 2026-09-18) — the one defect, six costumes

There is one pane renderer, `paneListRow(activePaneList)` (`ContentView+SidebarLayout.swift:225`),
but **the Library leaf does not mount the Library** — it mounts `contentWithOptionalModeRail`
→ `contentView` (`PaneSpec:123-127` → `ContentView+SidebarLayout.swift:186-191` → `Nav:168`),
and `contentView` is the OLD mode router: `if sidebarMode == .knowledgeGraph … else if
sidebarMode == .research … else switch viewMode` (`Nav:173-376`). Every "takeover" the
maintainer observed — workflow editor, the legacy KG browser (`OntologyBrowser`), the
research project list, the Automation placeholder, chain/batches/activity/comparison — is
the SAME defect: the mode switch lives inside the Library pane's content, not beside it.

Three more facts complete the diagnosis:

- **The Mac Preview pane never consults the mode.** `widescreenCanvasPaneContent`
  (`Detail:71-138`) has no `viewMode` branch — it hands whatever document is around to
  `EditorView`, so a workflow renders as a glyph instead of its canvas. (The mode-switch at
  `Detail:244-323` is mounted only by the COMPACT/iOS flow, `ContentView+CompactReader.swift:102`.)
- **`PaneContentPlan` exists and is exhaustive but is read only for empty-state strings.**
  It is the (selection kind × pane) matrix (`Plan:22-170`), consulted at exactly two call
  sites, both cosmetic (`Detail:319`, `Detail:398`). Its `library: .content` for every row
  currently ENCODES the takeover rather than describing the ruled Library-always-navigator
  intent — that is the one-line change this program makes real.
- **The stale "Chat Scope" inspector leak.** `handleSidebarModeChange` (`Mods:307-321`)
  normalizes `viewMode` for library/chat/workflows/automation/activity but, for
  `.research`/`.knowledgeGraph`, deliberately leaves `viewMode` untouched (comment: "No
  ViewMode case; contentView intercepts on sidebarMode, so leave viewMode untouched",
  `Mods:316-319`) and the Sidebar menu writes only `sidebarMode`
  (`ViewMenuCommands.swift:207,222`) — never `viewMode`. Open a chat (`viewMode=.chat`),
  press ⌃⌘9 or ⌃⌘8: the centre shows KG/Research via the `sidebarMode` intercept, but the
  Inspector still switches on `viewMode` (`Detail:366`) and shows `ChatInspector` — a stale
  "Chat Scope" tab for a selection that is no longer a chat. The same root cause leaks
  through "Show in Graph" (`ContentView+RootLayout.swift:484-486`) and the AppleScript `kg`
  verb (`ContentView+StateEvents.swift:474-478`).

Two axes drive routing today and they can disagree: `sidebarMode`
(`@SceneStorage("sidebarMode")`, `ContentView.swift:340`) and `viewMode: AppViewMode`
(persisted as `@SceneStorage("viewModeType")` + `"viewModeItemId"`,
`ContentView.swift:225-226`). The migration's throughline is collapsing routing onto ONE
axis (`AppViewMode`, read through `PaneContentPlan`) and demoting `sidebarMode` to, at most,
a sidebar filter.

## THE MATRIX — selection kind × surface

Every `AppViewMode` case the review's inventory names, against the four surfaces, with the
ruled rendition in each cell. `library` is a CONSTANT column — every row shows the same
`.libraryBrowser` — because "the Library pane never becomes the selected thing" is exactly
the ruling this table exists to make assertable.

| Selection (`AppViewMode`) | Library | Source/Preview | Reader | Inspector |
|---|---|---|---|---|
| `.library` (entities/claims/folder rows) | Library browser | honest empty / doc preview | honest empty | Document Inspector — **[OK]** already correct (`ContentView+StateLayout.swift:102-108`, `LibraryView+ContentBranches.swift:176-241`) |
| `.workflow(x)` | Library browser — **[PROPOSED]** | Workflow canvas (`WorkflowEditor`) — **[PROPOSED]**, today full-width in Library (`Nav:286-294`) | Last/current run log — **[PROPOSED]**, today an honest empty state (`ReadingPaneView+Tabs.swift:155-169`) | Palette · node · runs (`WorkflowInspector`, 3 tabs) — **[OK]** already correct (`Detail:384-390`) |
| `.chat` | Library browser — **[OK]** already correct (`Nav:237-244`) | document preview | thread/document | Sources · Plan · Knowledge · Compare (`ChatInspector`/`ChatSurfaceTab`) — **[PARTIAL]**, correct kind but duplicated (§Inspector policy) |
| research (project selection) | Library browser — **[PROPOSED]**, today a bespoke `HStack{ResearchProjectListView\|ResearchWorkspaceView}` (`Nav:201-221`) | document preview | thread/document (via chat's Plan tab) | Sources · Plan · Knowledge · Compare — **[PROPOSED]** |
| `.comparison` | — **RETIRED** (CD 2026-09-18): `AppViewMode.comparison`/`ComparisonDetailView` are deleted (increment 4); comparison becomes two sibling artifacts shown as two Reader panes with a diff lens, not a mode/node/view of its own — see `m2p.comparison-is-panes-and-diff-lens` | | | |
| `.chain` | Library browser — **[PROPOSED]**, today `ChainEditorView`/stub (`Nav:310-319`) | node detail (chain) | — | honest empty (`Detail:392`) |
| `.batches` / `.batch` | Library browser — **[PROPOSED]**, today `BatchRunView()`/placeholder (`Nav:321-331`) | node detail | — | honest empty; `.batch` case retires (`SelH:283` restore already maps `"batch"`→`.activity`) |
| `.automation` | Library browser — **[PROPOSED]**, today a placeholder (`Nav:333-338`) | node detail (nothing selected → Library alone, no takeover) | — | "Nothing to Show" (`Plan:139-145`) |
| schedule / trigger | Library browser — **[PROPOSED]**, today `ScheduleDetailView`/`ScheduleEditorView`/`TriggerDetailView`/`TriggerEditorView` (`Nav:340-352`) | node detail | — | honest empty |
| `.activity` | Library browser — **[PROPOSED]**, today `ActivityWindowLauncherView` (`Nav:354-374`) | node detail (run) | — | honest empty |
| KG map / timeline | existing Library **view modes** (`.timeline`, `.geoMap`, `ContentView+StatePreview.swift:306-318`) on the Entities collection — **[PROPOSED]** | — | — | entity inspector, when one entity is focused |
| KG set-level graph | retires with `OntologyBrowser` — **[PROPOSED]**; an entity's ego-network may return later as a Source rendition, not a Library takeover | ego-network graph (future, one entity only) | — | entity inspector |
| entity / claim row (KG table) | Library table row — **[OK]** already correct | document preview | — | entity inspector (a real inspector surface, ties `kg-entity-inspector`) |

Schedules and research projects are **sidebar nodes**, exactly like workflows — not Library
table rows — so they gain a Library-pane rendition, not a special-cased list view.

## Inspector policy — the plan picks the SURFACE, not a unified tab enum

`PaneContentPlan.plan(for: viewMode).inspector` names which inspector SURFACE mounts for the
current selection (document / workflow / chat / entity / …). Each surface keeps its OWN tab
enum and its own `availableTabs` — `InspectorTab` (private static `availableTabs(for:
Document?)`, `Views/Inspector/Document/DocumentInspector+TabBar.swift:129`),
`WorkflowInspectorTab.availableTabs` (`Views/Workflow/Inspector/WorkflowInspector.swift:95`),
`ChatSurfaceTab`. **Do not unify these enums** — three surfaces, three tab vocabularies, and
forcing one enum would either lose a surface's tabs or grow dead cases on the others. The
one thing that must be pure and testable is the SURFACE choice one level up; making
`DocumentInspector.availableTabs` internal (rather than private) is what lets that be tested.
This already yields "tabs shown only for the kind that is selected" without inventing a
fourth type.

## Behaviors (one id per rule, each tagged with its pinning test)

- `m2p.library-is-always-navigator` — **[PARTIAL]**, #4705: the matrix's `library` column has
  stated the constant `.surface(.libraryBrowser)` for every row since increment 1
  (4132ca589), and increment 2 (this commit) made it TRUE at runtime for `.workflow`
  (`WorkflowEditor` dropped from the regular-width arm's allowlist) — but `.comparison`,
  `.chain`, `.batches`/`.batch`, `.automation`, `.schedule`/`.trigger`, `.activity` still
  literally take over the Library pane pending increments 3-5, so the rule is not yet true
  everywhere. Pinned by the **shrinking-allowlist source guardrail**
  (`LibraryPaneNeverMountsModeSurfaceTests`, currently 8 tokens remaining, `WorkflowEditor(`
  dropped this increment) with a fixture proving the rule actually fires (per the
  guardrails-must-match-granularity ruling — never a rule that could pass vacuously), plus
  `PaneContentPlanTests.theLibraryColumnIsAlwaysTheBrowser` for the stated-constant half.
- `m2p.inspector-follows-selection` — **[OK]** (increment 0, a5528a977) the Inspector's
  surface is a pure function of the current selection kind and agrees with
  `PaneContentPlan`'s `.inspector` cell for every `SidebarMode` × `AppViewMode`
  combination — no stale kind survives a sidebar-mode change (the "Chat Scope" leak this
  closed: switching to Research/Knowledge Graph while a chat was selected used to leave
  `ChatInspector` on screen). Pinned by `ViewModeNormalizationTests` — the exhaustive
  `SidebarMode` × representative-`AppViewMode` table (`normalizedResultBelongsToNewMode`)
  plus the two regression pins (`chatToResearchDropsChatViewMode`,
  `chatToKnowledgeGraphDropsChatViewMode`).
- `m2p.workflow-canvas-in-preview` — **[OK]** (increment 2, 91b3d388c) selecting a workflow renders its
  canvas in the Source/Preview pane, not the Library pane; the Library stays the navigator
  beside it. A pin still wins first; at most one `WorkflowEditor` mount per workflow
  (`PaneSurface.allowsSplit` declines the split affordance, `\.isSecondarySplitPane` refuses
  a second render-time mount regardless of how a duplicate Preview leaf came to exist — two
  editors on one `editingWorkflow` binding would race their autosave tasks). Pinned by
  `PaneContentPlanTests.workflowUsesItsOwnPreviewAndReaderSurfaces` (library `.libraryBrowser`,
  preview `.workflowCanvas`), `PaneContentPlanTests.onlyWorkflowCanvasRefusesSplit`, and
  `LibraryPaneNeverMountsModeSurfaceTests.regularWidthWorkflowArmNeverMountsEditor` (the
  shrinking-allowlist guardrail, `WorkflowEditor(` dropped).
- `m2p.workflow-reader-is-run-log` — **[OK]** (increment 2, 91b3d388c) the Reader shows the workflow's
  run log (`WorkflowOutputLog`, an existing component with its own honest "no run yet" empty
  state, previously unused in production), replacing the old "Workflows Have No Transcript"
  dead end; a loading spinner covers the async fetch gap so the pane never goes blank. Pinned
  by `PaneContentPlanTests.workflowUsesItsOwnPreviewAndReaderSurfaces` (reader
  `.workflowRecipe`) at the policy level — NOTE: no automated SwiftUI-render test exists yet
  asserting `ReadingPaneView` actually mounts `WorkflowOutputLog` for a `.workflow` selection
  (a coverage gap, flagged for follow-up, not silently claimed as pinned).
- `m2p.kg-graph-retires-as-library-takeover` — **[OK]** (increment 3, 617233ec5) `SidebarMode.knowledgeGraph`
  and `OntologyBrowser` no longer mount inside the Library pane, or exist anywhere in the app
  target; timeline/map are (and already were, independent of this increment) ordinary Library
  view modes on the Entities collection. The force-directed graph surviving as a Preview
  rendition of one focused entity is NOT part of this increment — `ForceDirectedGraphView`
  still only reaches the user via `DocumentKGSurface` (Reader), unchanged; that promotion is
  future work, tracked separately, not blocked by anything here. The W3C SPARQL console the
  retired `OntologyBrowser` also hosted was EXTRACTED, not retired (creative director,
  2026-06-25 ruling #2593/#2614: "SPARQL is wanted and must be made VISIBLE; never delete it")
  — its own file (`Views/SPARQLConsole/SPARQLConsoleView.swift`) and window
  (`Window("SPARQL Console", id: "sparql-console")`, `FicheroApp.swift`), reached from the
  Knowledge menu. The "predict entities" flow (`HeuristicReviewSheet`) was NOT recovered — it
  had no caller outside the deleted files and is now unreachable anywhere; the dead-code sweep is #4791, and whether the predict
  affordance returns is the `kg-enrichment` milestone's decision (→ #4759), not silently dropped. Pinned by
  `SidebarModeRestoreTests.allCasesCountIsSix` (no `.knowledgeGraph` case),
  `LibraryPaneNeverMountsModeSurfaceTests.deletedTypesDoNotLingerAnywhere` (bare-identifier
  guardrail), and `KnowledgeGraphInspectorSectionTests.testSparqlConsoleUsesTypedQueryOpsThroughAStore`
  (re-pointed at the new console file, same invariant).
- `m2p.automation-nodes-in-preview` — **[PROPOSED]** schedule / trigger / chain / batches /
  activity selections render their detail in Source/Preview, never the Library pane; an
  automation selection with nothing chosen leaves the Library showing, not a placeholder
  screen. Pinned by the matrix rows for those kinds + the shrinking allowlist guardrail.
- `m2p.research-is-sidebar-node` — **[PROPOSED]** research projects are sidebar nodes like
  workflows, not a bespoke `HStack` container; a project's workspace content is reached via
  chat's Plan tab or a Preview rendition, and the Library pane never shows
  `ResearchProjectListView`. Pinned by the matrix row + the guardrail dropping
  `ResearchWorkspaceView(`.
- `m2p.chat-single-mount` — **[PROPOSED]** `ChatView(` appears in exactly one builder at a
  time — dock OR pane, never both — because conversation state (`currentConversation`,
  `backendConversationId`, `ChatView.swift:61-66`) is lifted out of `@State` into the
  per-window model before chat becomes movable. Pinned by `ChatPlacementTests` (never two
  mounts) + a guardrail "`ChatView(` appears in exactly one builder".
- `m2p.chat-scope-lives-in-both` — **[PROPOSED]**, renamed from `m2p.chat-scope-inspector-only`
  (creative director, 2026-09-18, supersedes it): chat scope lives in BOTH the Inspector's
  Sources tab (`ChatInspector`) AND the chat dock's own Sources view — the dock's Sources tab
  is NOT deleted. Pinned by a guardrail asserting BOTH mounts exist (the inverse of the old
  "exactly one call site outside its own file" rule).
- `m2p.comparison-is-panes-and-diff-lens` — **[PROPOSED]**, renamed from
  `m2p.comparison-folds-into-chat-compare` (creative director, 2026-09-18, supersedes it):
  `AppViewMode.comparison` and `ComparisonDetailView` are DELETED (increment 4, not 6) — but
  chat's Compare tab is NOT where comparison lives either. A "run with A and B" action leaves
  two sibling artifacts; the Compare workspace shows them in two Reader panes with a diff
  lens — comparison is about two prompts'/workflows' outputs, not a conversation. Pinned by a
  matrix row (no `.comparison` surface) + a guardrail that `ComparisonDetailView` does not
  appear in the app target + a Reader diff-lens test once the lens exists.
- `m2p.inspector-empty-shows-container-info` — **[PROPOSED]** with nothing selected, the
  Inspector shows the CONTAINER's info (the current folder/library), never a "Nothing to
  Show" placeholder; the `.inspector` pane kind stays hidden from the kind-switcher menu
  until it is a real leaf (increment 7). Pinned by an Inspector-empty-state test.
- `m2p.pane-head-parity` — **[PARTIAL]**, #4705 increment 6: every REAL-leaf pane head mounts
  the kind selector — Library, Preview and the Reader do (d8621ecc3: the Reader's
  `collapsesKindIntoLens` merged rung folded the real kind-switch options into its existing
  lens menu, restoring parity without a second icon); the kind-switcher's own menu offers
  only `PaneSpec.Kind.selectableKinds` (`.inspector`/`.chat` filtered out — both still
  placeholder leaves). Chat still has no pane head to mount one on — it gains one only when
  it becomes a movable pane (increment 6). Pinned by
  `PaneHeadKindSwitcherParityTests.everyRealLeafPaneHeadMountsPaneKindSelector` (source
  guardrail over the three real-leaf head files) and
  `PaneHeadKindSwitcherParityTests.selectableKinds*` (the filtered-kinds pins).
- `m2p.pane-toggles-everywhere` — **[GAP]**, ISSUE #4779: the toolbar's pane-visibility
  toggles (`ContentView+StateLayout.swift`'s `showsPaneToggles`) are gated on
  `sidebarMode == .library`, so they stay hidden for `.chat` and, since increment 2, for
  `.workflows` too — even though both now have a real Library + Preview + Reader shape with
  genuine content to toggle. Not fixed by increment 2 (Workflows lands in the same
  already-accepted state Chat has been in since before this migration; the gap predates and
  is not caused by this program). Recommendation: widen `supportsReadingWorkspace`/
  `showsPaneToggles` past library-only once a mode's panes carry real content, tracked
  separately on #4779.

## Migration — nine increments (0–8), each shippable, each with its pinning test

Serial in one lane for `Nav`/`Detail`/`Plan` — they are touched repeatedly across
increments 2, 4, and 5.

- **0. Fix the inspector leak (no ruling needed).** Extract pure
  `normalizedViewMode(current:forNewSidebarMode:) -> AppViewMode?` from
  `handleSidebarModeChange` (`Mods:307-321`); `.research`/`.knowledgeGraph` map to
  `.library(nil)` unless already library. Files: `Mods` + new
  `Tests/Unit/general/Views/Shell/SidebarModeViewModeAgreementTests.swift`. Deletes the
  "leave viewMode untouched" arm. Persistence: none. Test: `m2p.inspector-follows-selection`.
- **1. The matrix names its surfaces (pure, no behaviour change).**
  `PaneContentPlan.Cell.content` grows from `content | empty(String)` to `surface(PaneSurface)
  | empty(String)`, where `PaneSurface` enumerates `libraryBrowser, documentPreview,
  workflowCanvas, nodeDetail, documentReader, workflowRecipe, documentInspector,
  workflowInspector, chatScope, entityInspector`; the matrix's `library` column becomes the
  constant `.surface(.libraryBrowser)` for every row. Files: `Plan`, `PaneContentPlanTests.swift`,
  the two readers at `Detail:319,398`. Deletes nothing. Test: existing matrix test + "every
  row's cell is a surface or a non-empty reason".
- **2. Workflow canvas → Preview pane; Library stays Library.** `Nav`'s `.workflow`
  regular-width arm becomes the same `LibrarySplitPaneHost` pattern as `.chat` (`Nav:237-244`);
  `Detail:71` gains a first branch for `.workflow` → `WorkflowEditor`; matrix row updates.
  Also: `showsPaneToggles` stops gating on `sidebarMode == .library`
  (`ContentView+StateLayout.swift:25-27`). Files: `Nav`, `Detail`, `Plan`,
  `ContentView+StateLayout.swift`, `ContentView+StatePreview.swift`. Deletes: the "Select a
  Workflow" placeholder (`Nav:296-304`). Needs the no-collapse ruling below (open question 2)
  or selecting a workflow in a Browse workspace with no Preview leaf shows nothing. Test:
  `m2p.workflow-canvas-in-preview`, `m2p.library-is-always-navigator` (drop `WorkflowEditor(`).
- **3. Delete Knowledge Graph MODE — DONE (2026-09-18).** Removed `SidebarMode.knowledgeGraph`,
  `Nav:173-175`, the menu item (`ViewMenuCommands.swift`), the Ontology view-mode menu
  (`ViewMenuLayoutSections.swift`, `KnowledgeGraphViewModeSection` + its
  `\.knowledgeGraphViewMode` FocusedValues entry); re-pointed "Show in Graph"
  (`ContentView+RootLayout.swift`) and AppleScript `kg` (`ContentView+StateEvents.swift`) at
  the library-wide entities table (`sidebarSelectionState.selectedItemId = "entities-browser"`).
  Moved `isOcrGarbage` to `Models/EntityNameHeuristics.swift` (the only one of `OntologyBrowser`'s
  filter helpers with a caller outside itself — `parseHiddenKinds`/`filterEntities`/`isDateEntity`
  had none and retired with the file) before deleting the 6 confirmed-safe `OntologyBrowser*`
  files and their 2 test files. **The SPARQL console (#3298) was EXTRACTED, not deleted** — a
  standing creative-director ruling (2026-06-25, #2593/#2614) requires it stay visible; it was
  NOT part of the review's original delete list and surfaced only once the deletion exposed it
  had no other caller. Now its own file/window, reached from the Knowledge menu. **Persistence:**
  a window saved with `sidebarMode == "knowledgeGraph"` restores to `.library` — routed through
  `SidebarMode.restored(from:)` (not `RawRepresentable.init(rawValue:)`'s unproven default
  fallback), landed in increment 3a ahead of the deletion itself. Test:
  `m2p.kg-graph-retires-as-library-takeover` + `SidebarModeRestoreTests` (the restore table).
- **4. Automation / schedule / trigger / chain / batches / activity / batch → Preview-pane
  node detail. Also: Comparison retires (CD 2026-09-18 ruling).** Same move as increment 2,
  row by row. Delete `AppViewMode.batch` (SelH:283 already redirects to `.activity`), the
  `.automation` placeholder arm, the "Create Chain" stub (`Nav:313-318`). Delete
  `AppViewMode.comparison` and `ComparisonDetailView`'s mount (`Nav:245-250`) — comparison
  becomes two sibling artifacts shown as two Reader panes with a diff lens (not a mode, not
  chat's Compare tab; see `m2p.comparison-is-panes-and-diff-lens`) — the diff-lens UI itself
  is a separate, not-yet-scoped follow-up; this increment only removes the retired mode/view.
  Files: `Nav`, `Detail`, `Plan`, `Models/SidebarViewTypes.swift`, `SelH`,
  `ContentView+Persistence.swift`. **Persistence:** `restoreViewMode`
  (`ContentView+Persistence.swift:60-100`) keeps accepting the retired strings (`"batch"`,
  `"batches"`, `"automation"`, `"comparison"`) exactly as it already does for `"search"`.
  Test: `m2p.automation-nodes-in-preview`, `m2p.comparison-is-panes-and-diff-lens` + a
  restore-table test.
- **5. Research stops being a centre takeover.** Delete the `HStack` container +
  `ResearchProjectListView` mount (`Nav:176-222` regular arm); projects become sidebar
  selections; workspace content reached via chat's Plan tab or a Preview rendition. Files:
  `Nav`, `Views/Chat/Research/*`, sidebar section files. Highest product ambiguity — do not
  start before the Q1-equivalent design confirmation the epic's rulings already settled
  (research projects are sidebar nodes). Test: `m2p.research-is-sidebar-node`.
- **6. Chat movable as a pane.** Lift `ChatView`'s `@State currentConversation` /
  `backendConversationId` (`ChatView.swift:61-66`) into the per-window model; add
  `ChatPlacement.resolve(paneListHasChatLeaf:showChatPane:) -> .dock | .pane(leafID) |
  .hidden`; replace the `.chat` placeholder (`PaneSpec:167-179`). The Sources tab vs.
  `ChatInspector` do NOT de-duplicate (CD 2026-09-18 supersedes the earlier "Inspector only"
  plan: chat scope lives in BOTH places — see `m2p.chat-scope-lives-in-both`). Comparison is
  NOT this increment's concern either (CD 2026-09-18: it retired in increment 4 as panes + a
  diff lens, never folded into chat's Compare tab — see
  `m2p.comparison-is-panes-and-diff-lens`). Files: `Views/Chat/*`, `PaneSpec`,
  `ContentView+SidebarLayout.swift`. Persistence: `showChatPane`, `sidebar.chat.height`
  unchanged; confirm `chatPaneWidth` (`ContentView.swift:360`) still has a reader before
  keeping it. Also delivers `m2p.pane-head-parity` for Chat. Test: `m2p.chat-single-mount`,
  `m2p.chat-scope-lives-in-both`.
- **7. Inspector as a real leaf.** Last — it anchors the inspector toggle and the system
  search toolbar item (`ContentView+InspectorContainer.swift:35-103,60-86`). Ship the leaf
  only once the toolbar-anchor risk (§Risks) is resolved without a double mount. Test:
  `m2p.inspector-empty-shows-container-info`.
- **8. Move the mode switch to compact.** Once no regular-width arm remains, `contentView`'s
  switch relocates to `ContentView+CompactReader.swift` (it is ALSO the compact/iOS root,
  `ContentView+CompactReader.swift:90`, with three push stacks — it MOVES, it is not
  deleted); the Library leaf mounts `LibrarySplitPaneHost` directly; the shrinking-allowlist
  guardrail's allowlist is empty. Test: `m2p.library-is-always-navigator` at its final,
  empty-allowlist state.

## Persistence

Four stored mode-string keys name a mode and must tolerate every case this program retires:
`sidebarMode` (`@SceneStorage`, `ContentView.swift:340`), `viewModeType` +
`viewModeItemId` (`@SceneStorage`, `ContentView.swift:225-226`), nav-history `viewType`
(`ContentView+NavigationHistory.swift:35`), and `WindowSeed.viewModeType`
(`App/WindowSeed.swift:25-26`, `App/LibraryWindow+Actions.swift:34,145`). The rule, per
retired case: a **tolerant decode + a pinned restore-table test**, exactly the pattern
`restoreViewMode` already uses for `"search"` (`ContentView+Persistence.swift:69-72`) — a
saved window with a retired mode string restores to its successor (e.g.
`"knowledgeGraph"` → `.library`, `"batch"`/`"batches"`/`"automation"` → their successors),
never crashes and never blanks. Do not rely on `RawRepresentable.init(rawValue:)`'s silent
default-fallback for `SidebarMode` — route restore through an explicit
`SidebarMode.restored(from: String)` so the fallback is a tested decision, not an
accident of `Codable` synthesis.

## Risks (from the review)

- **Width.** `WorkflowEditor` gets the full centre today (`Nav:293`); a Preview leaf may be
  ~40% (`PaneSpec:296` fallback). Canvas zoom-to-fit and node-palette drag need checking at
  that width; a "Build" built-in workspace (wide preview) is the mitigation, not a mode.
- **Drag-drop.** Palette → canvas crosses the inspector-to-centre column boundary
  (`WorkflowInspector.onAddNode` → `addNodeFromTool`, `Detail:385-389`); chat-scope drops
  land on `ChatView`/`ChatInspector`. Preview-pane hosting wraps content in
  `PreviewSplitPaneHost` + tap-gesture focus seams that need checking for drop-swallowing.
- **Preview pin / split.** A pinned preview must not be replaced by a workflow canvas
  (`Detail:80-92` must keep winning first). A split preview mounting TWO `WorkflowEditor`s
  on one `$editingWorkflow` risks double-autosave (`WorkflowEditor.swift:17-21`, unproven
  hypothesis) — disable split for non-document surfaces until confirmed safe.
- **Undo / keyboard focus.** `WorkflowEditor` registers `@Environment(\.undoManager)`
  (`WorkflowEditor.swift:47-48`); once the Library sits beside the canvas in one window,
  ⌘Z's target depends on `focusedPane`, and ⌘A/focused-command menus read
  `\.focusedPaneKind` — verify Select All/Delete inside the canvas route correctly.
  `WorkflowEditor`'s zoom-to-fit and node-palette drag at reduced width are the same
  concern as the Width risk above.
- **Toolbar.** Pane toggles are hidden outside library mode (`ContentView+StateLayout.swift:25-27`);
  per-mode display-mode lists and View-menu sections keyed on `sidebarMode`
  (`ViewMenuLayoutSections.swift:14-24,155,217-226`) all assume takeover and need an
  explicit per-increment decision, not a default.
- **`AnyView` erasure / environment traps.** `Nav:280-285` and `Detail:182-194` carry
  LOAD-BEARING `AnyView` erasure (#4331) — moving branches between builders changes composed
  type depth; keep erasure at each new case boundary. Any view re-hosted across a column
  boundary needs `windowEnvironment`/`libraryServiceEnvironment` (the pane path already
  applies this per leaf, `PaneSpec:246`); the Inspector column is a separate boundary and
  is the #4703 class of trap.
- **Compact/iOS.** Everything above is regular-width only; the compact push stacks must
  keep working unchanged (increment 8 moves, never rewrites, them).
- **Restoration.** Covered above (§Persistence) — every retired case needs a tolerant
  decode or a saved window restores into a crash or blank.

## Rulings (creative director, 2026-09-18, second round — close the five former open questions)

All five questions this section used to ask are now decided. None of the five is [OK] yet on
its own — each lands with the increment named below; this section records the DECISION, not
the implementation status (see the Behaviors list above and the Migration increments for that).

1. **⌃⌘1…9 do NOT survive as "modes."** The Sidebar-mode menu entries are **removed** — not
   "reveal that sidebar section," not filters, removed outright. Superseded the review's own
   "reveal + focus" recommendation. Only ⌃⌘9's removal (the KG entry) is part of THIS epic's
   current scope (increment 3, done); the other six chords (⌃⌘1/3/4/5/6/8) retire with their
   own modes across increments 4-6, not before — `SidebarModeButton`'s checkmark/radio
   semantics and the per-mode sidebar widths/display modes
   (`ContentView+StateLayout.swift:55-68`) go with them. **Zoom to Fit stays ⌘9** — a
   different chord, no collision.
2. **A workflow selected in a workspace with no Source/Preview leaf: an Open affordance adds
   the pane; nothing moves automatically.** Confirms the review's own recommendation — the
   Library stays, the Inspector shows the workflow inspector, an explicit Open (double-click
   / Return) adds a Preview leaf, the same verb as opening a document. The no-collapse-by-
   selection ruling applied at its sharpest edge: an auto-rearranging layout would violate
   "the workspace is the source of truth."
3. **Chat scope lives in BOTH the Inspector's Sources tab AND the chat dock's Sources view.**
   Supersedes the review's "Inspector only" recommendation — retitled to
   `m2p.chat-scope-lives-in-both` below (no more "delete the dock's duplicate Sources tab").
4. **Comparison = panes + a diff lens. No Comparison view, node or window.** A "run with A
   and B" action leaves two sibling artifacts; the Compare workspace shows them in two Reader
   panes with a diff lens. `ComparisonDetailView` and `AppViewMode.comparison` are DELETED
   (increment 4's scope) — but chat's Compare tab is NOT their replacement either; comparison
   is about two prompts' or two workflows' outputs, not a conversation. Supersedes the
   review's "folds into chat's Compare tab" recommendation — retitled to
   `m2p.comparison-is-panes-and-diff-lens` below, moved to increment 4 (not 6). Loove stays
   its own window (a diagnostic matrix, unrelated).
5. **Inspector with nothing selected = the container's Info.** Confirms the review's own
   recommendation — never "Nothing to Show"; the Inspector stays the native trailing column
   for now, and the `.inspector` pane kind stays hidden from the kind-switcher menu
   (`PaneSpec.Kind.selectableKinds`) until increment 7 makes it a real leaf.

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | y | `normalizedViewMode`, `PaneContentPlan.Cell.surface`, `ChatPlacement.resolve`, `SidebarMode.restored(from:)` | `fichero/Tests/Unit/general/Views/Shell/*Tests.swift` |
| Availability (Swift) | y | pane-head kind-switcher present on every pane head | `fichero/Tests/Unit/general/Views/Shell/<PaneHeadParity>Tests.swift` |
| Backend (pytest) | n | — | — |
| MCP | n | — | — |
| CLI | n | — | — |
| Click-around (XCUITest, Mac) | y | select a workflow/chat/entity, assert Library unchanged + correct Preview/Reader/Inspector content | `fichero/Tests/UI/general/<ModesToPanes>FlowUITests.swift` |
| iPhone (iOS) | n (compact path moves, not redesigned, in increment 8) | — | — |
| iPad | n (same) | — | — |
| Load (#4634) | n | — | — |

## Accessibility identifiers

Reuse existing pane-head and inspector-tab identifiers where they already exist
(`WorkflowInspectorTab`, `ChatSurfaceTab`); the click-around leg needs, at minimum:
- `library.pane` — confirms the Library leaf's identity is stable across selections
- `pane.kindSwitcher` — the per-pane-head kind selector (`m2p.pane-head-parity`)
- `inspector.surface.<kind>` — which inspector surface is mounted, for the agreement test

## Open questions (per-file: what was not grounded in the review)

Nothing in this spec's Behaviors/Migration/Risks/Persistence sections goes beyond a claim
the review verified with a file:line citation. The five Open Questions above are the
review's own recommendations where the epic asked the creative director to decide; nothing
was invented outside that set.
