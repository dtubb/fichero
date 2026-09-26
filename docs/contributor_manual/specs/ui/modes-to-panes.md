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
| `.chat` | Library browser — **[OK]** already correct (`Nav:237-244`) | document preview | `.surface(.documentReader)` — **[OK]** (4b-1 audit, 2026-09-18): the row previously said `.empty("A conversation has no reader view.")`, which was WRONG but harmless while nothing read this cell — a conversation keeps Library + Source + Reader all showing real documents (the modes-to-panes ruling), so once 4b-1 made the Reader obey the cell, the old value would have blanked it for every chat user. Corrected before the regression shipped. | Sources · Plan · Knowledge · Compare (`ChatInspector`/`ChatSurfaceTab`) — **[PARTIAL]**, correct kind but duplicated (§Inspector policy) |
| research (project selection) | Library browser — **[PROPOSED]** (5b), today a bespoke `HStack{ResearchProjectListView\|ResearchWorkspaceView}` (`Nav:201-221`) | `PaneSurface.webBrowser` (`ResearchBrowserPane`) when no document is also selected, else document preview — **[PROPOSED]** (5c, DECIDED design per CD ruling 2026-09-18: scratch browsing persists nothing, only an explicit save makes a node) | thread/document (via chat's Plan tab, 5b) | Sources · Plan · Knowledge · Compare — **[PROPOSED]** (5b) |
| `.comparison` | — **RETIRING** (CD 2026-09-18 ruling; scope clarified 2026-09-18: split OUT of increment 4a into increment 4c below): the comparison VIEW/mode/window (`AppViewMode.comparison`/`ComparisonDetailView`) retires, but the PRODUCING "run with A and B" action survives — it leaves two sibling artifacts shown as two Reader panes with a diff lens, not a mode/node/view of its own — see `m2p.comparison-is-panes-and-diff-lens`. Three sites still construct `.comparison` today | | | |
| `.chain` | Library browser — **[OK]** (increment 4a, 9128ecdee) | node detail (chain, `ChainEditorView`) — **[OK]** (increment 4a); "Create Chain" empty state MOVED here, not deleted | — | honest empty |
| `.batches` | Library browser — **[OK]** (increment 4a) | node detail (`BatchRunView`) — **[OK]** (increment 4a) | — | honest empty; `AppViewMode.batch` DELETED (increment 4a) — a persisted `"batch"` still restores to `.activity` (`ContentView+Persistence.swift`'s `case "batches", "batch":`) |
| `.automation` | Library browser — **[OK]** (increment 4a) | node detail (nothing selected → Library alone, no takeover) — **[OK]** (increment 4a) | — | "Nothing to Show" (`Plan:139-145`) |
| schedule / trigger | Library browser — **[OK]** (increment 4a) | node detail (`ScheduleDetailView`/`ScheduleEditorView`/`TriggerDetailView`/`TriggerEditorView`) — **[OK]** (increment 4a) | — | honest empty |
| `.activity` | Library browser — **[OK]** (increment 4a); `ActivityWindowLauncherView` DELETED, replaced by `ActivityDetailView` mounted directly | node detail (run, `ActivityDetailView`) — **[OK]** (increment 4a); nothing selected → new honest empty state ("Select a run in the sidebar to see its details.") | — | honest empty |
| KG map / timeline | existing Library **view modes** (`.timeline`, `.geoMap`, `ContentView+StatePreview.swift:306-318`) on the Entities collection — **[PROPOSED]** | — | — | entity inspector, when one entity is focused |
| KG set-level graph | retires with `OntologyBrowser` — **[PROPOSED]**; an entity's ego-network may return later as a Source rendition, not a Library takeover | ego-network graph (future, one entity only) | — | entity inspector |
| entity / claim row (KG table) | Library table row — **[OK]** already correct | the cited page, span highlighted, revealed via `focusKGSourcePreview` without changing the current selection — **[GAP]** (→ #4838; today plain document preview, no span/reveal) | the readable paragraph, drawn from the entry composer's `sentences[]` — **[GAP]** (→ #4838; today honest empty — prerequisite: #4804, since the plan's `entitySelection` is a Bool and cannot say WHICH entity/claim is focused, and the Reader rendition needs that payload) | KG curation (statements list, merge, aliases, history) unchanged — **[OK]** already correct, ties `kg-entity-inspector` |

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
  (4132ca589); increment 2 made it TRUE at runtime for `.workflow`, increment 3 for the
  retired KG graph mode, and increment 4a, 9128ecdee for
  `.chain`/`.batches`/`.schedule`/`.trigger`/`.activity` (`BatchRunView(`/`ChainEditorView(`/
  `ScheduleDetailView(`/`TriggerDetailView(`/`ActivityWindowLauncherView(` all dropped from
  the regular-width arm's allowlist; `ActivityWindowLauncherView` deleted outright) — but
  `.comparison` (retires in increment 4c) and research
  (increment 5, `ResearchWorkspaceView(`) still literally take over the Library pane, so the
  rule is not yet true everywhere. Pinned by the **shrinking-allowlist source guardrail**
  (`LibraryPaneNeverMountsModeSurfaceTests`, currently 2 tokens remaining:
  `ResearchWorkspaceView(`, `ComparisonDetailView(`) with a fixture proving the rule actually
  fires (per the guardrails-must-match-granularity ruling — never a rule that could pass
  vacuously), plus `PaneContentPlanTests.theLibraryColumnIsAlwaysTheBrowser` for the
  stated-constant half.
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
  2026-06-25 ruling: SPARQL is wanted, must stay visible, and is never deleted → #2593, → #2614)
  — its own file (`Views/SPARQLConsole/SPARQLConsoleView.swift`) and window
  (`Window("SPARQL Console", id: "sparql-console")`, `FicheroApp.swift`), reached from the
  Knowledge menu. The "predict entities" flow (`HeuristicReviewSheet`) was NOT recovered — it
  had no caller outside the deleted files and is now unreachable anywhere; the dead-code sweep is → #4791, and whether the predict
  affordance returns is the `kg-enrichment` milestone's decision (→ #4759), not silently dropped. Pinned by
  `SidebarModeRestoreTests.allCasesCountIsSix` (no `.knowledgeGraph` case),
  `LibraryPaneNeverMountsModeSurfaceTests.deletedTypesDoNotLingerAnywhere` (bare-identifier
  guardrail), and `KnowledgeGraphInspectorSectionTests.testSparqlConsoleUsesTypedQueryOpsThroughAStore`
  (re-pointed at the new console file, same invariant).
- `m2p.automation-nodes-in-preview` — **[OK]** (increment 4a, 9128ecdee) schedule /
  trigger / chain / batches / activity selections render their detail in Source/Preview,
  never the Library pane; an automation selection with nothing chosen leaves the Library
  showing, not a placeholder screen. `AppViewMode.batch` and `ActivityWindowLauncherView` are
  DELETED — zero remaining references to either, verified by type defined in file, not
  textual constructor grep. Pinned by the matrix rows for those kinds +
  `PaneContentPlanTests.nodeDetailModesLandInThePreviewSlot`, the shrinking-allowlist
  guardrail (`LibraryPaneNeverMountsModeSurfaceTests`, 5 tokens dropped this increment) with
  its `deletedBareIdentifiers` check for `ActivityWindowLauncherView`, and
  `ContentViewPersistenceTests.testRetiredBatchStringStillRestoresToActivity` for the
  persisted-`"batch"`-string tolerant decode.
- `m2p.research-is-sidebar-node` — **[PROPOSED]**, split into increments 5a/5b/5c above
  (2026-09-18 design pass): research projects are sidebar nodes like workflows, not a bespoke
  `HStack` container; a project's workspace content is reached via chat's Plan tab (5b — the
  chat dock is scoped to the project via `ChatView(researchProject:)`, the same adapter
  `ResearchChatPane` already uses) or a Preview rendition (5c, the embedded browser as
  `PaneSurface.webBrowser` — DECIDED design per creative-director ruling 2026-09-18, see 5c
  above). Agent workspaces (folder Documents) get their own, simpler path (5a) — they need no
  new `AppViewMode` case, just sidebar visibility over Documents that already exist. The
  Library pane never shows `ResearchProjectListView`/`ResearchWorkspaceView` once all three
  land. Pinned by the matrix row + the guardrail dropping `ResearchWorkspaceView(`.
- `m2p.one-creatable-kinds-list-drives-both-menus` — **[BROKEN]** (#4853) ONE list of
  creatable node kinds should drive both the sidebar's + menu and File > New, so they cannot
  drift; each item creates the node in the selected folder and selects it, like New Folder.
  Verified BROKEN at HEAD: `AddItemMenu.swift` (the sidebar + menu) includes "New Trigger";
  `FocusedCommandButtons+CreationActions.swift` (File > New) offers Chat/Workflow/Chain/
  Comparison/Schedule — no Trigger. Two independent hand-written lists, not one shared source.
  With the Data menu retired, every node kind needs one menu-bar home; today Trigger has none
  via File > New. No fix in flight for this file as of this pass. Also unverified this pass
  (named in the issue, not independently traced): whether every existing + menu item actually
  creates its node end to end.
- `m2p.sidebar-menu-lists-modes-not-nodes` — **[GAP]** (#4854) the View menu's "Sidebar"
  section should retire once the remaining `SidebarMode` cases fold into the node model — under
  the ratified ruling, the Library is always the navigator and chats/workflows/schedules/
  triggers/chains are nodes in its tree, not sidebar modes to switch between. Verified at HEAD:
  `ViewMenuCommands.swift`'s `SidebarModeSection` (`:125-`) still renders Library/Chat/
  Workflows/Automation/Research as mode-switch buttons with keyboard shortcuts — the Knowledge
  Graph and batch modes already retired (`m2p.kg-graph-retires-as-library-takeover`), these
  five have not. Per the issue's own framing this is an honest picture of an UNFINISHED
  migration, not a bug introduced by this menu — tagged GAP (intended future state, not yet
  built), not BROKEN. No fix in flight for this file as of this pass. Open design question,
  not decided here: what replaces the keyboard shortcuts once the section goes — "reveal the
  first node of this kind" and "a kind filter on the Library" are the two candidates the issue
  itself names, and which kinds (citations, chains, triggers, schedules) deserve a top-level
  presence at all is undecided.
- `m2p.every-view-mode-routes-somewhere` — **[BROKEN]** (#4904) every `AppViewMode` case the
  sidebar/router can select must actually route to a real destination — a case that exists with
  no router arm is a silent dead end, the same class of defect as a mode that never got wired at
  all. A guardrail enforces this: `scripts/check_sidebar_items.py` scans `SidebarItem` factories/
  builders against `ContentView`'s router and is currently RED — 3 unwired item types: `batch`
  (the `AppViewMode.batch` case is missing entirely, not merely unrouted) and `schedule`/
  `trigger` (the `AppViewMode` cases exist; `ContentView`'s router has no matching case for
  either). Not traced to a specific commit — reads as part of the still-in-progress modes-to-
  panes increment 4a/4b work this spec already tracks elsewhere (schedules/triggers/batches
  opening as node detail). *Test:* the guardrail itself.
- `m2p.browser-is-a-source-rendition` — **[GAP]** (#4809): the embedded browser lives
  INSIDE the Source/Preview pane as `PaneSurface.webBrowser` — no browser pane kind, no tab
  strip of its own (creative-director ruling, 2026-09-18). Design decided, not yet built —
  see 5c above for the mechanism.
- `m2p.scratch-browsing-persists-nothing` — **[GAP]** (#4810): navigating to find a
  source (a search engine, a catalogue, any page visited while looking) persists NOTHING
  beyond a session-only back/forward trail — never a node (creative-director ruling,
  2026-09-18). The ruling is about PAGES; whether cookies and logins are also scratch is NOT decided —
  see 5c's note and #4810.
- `m2p.saving-a-source-makes-a-node` — **[GAP]** (#4811): only an explicit save makes
  a node — either the page as a native `.webarchive` (URL + capture time), or the page's
  EXTRACTED output saved as the artifact with the page as its provenance, preferred where it
  applies (creative-director ruling, 2026-09-18) — through the one audited action layer, same
  as every other save. Constrains research.md's Open Question 2 (the save action's design).
- `m2p.research-workspaces-are-library-folders` — **[OK]** (11368be12, #4812 closed): agent workspaces (`workspace_kind=agent` folder
  Documents) are already ordinary `Document`s and must behave as ordinary folders
  everywhere — sidebar visibility (already true, no new bucket or section needed), selection
  (fixed — the `isWorkspace` special case that diverted to the Research takeover is deleted),
  and creation placement (fixed — `createWorkspace` reuses `createFolder`'s own
  context-aware placement via a `parentId` parameter, the same code path, not a copy). See
  increment 5a above for the full mechanism. Pinned by
  `SidebarWorkspaceNodeTests.testWorkspaceSelectionNoLongerDivertsToResearch`,
  `.testCreateNewWorkspaceReusesFolderPlacementAndSelects`, `.testRegistryWiringIncludesWorkspace`,
  `.testResearchProjectListViewHasNoWorkspaceUI`.
- `m2p.chat-single-mount` — **[PROPOSED]** `ChatView(` appears in exactly one builder at a
  time — dock OR pane, never both — because conversation state (`currentConversation`,
  `backendConversationId`, `ChatView.swift:61-66`) is lifted out of `@State` into the
  per-window model before chat becomes movable. Pinned by `ChatPlacementTests` (never two
  mounts) + a guardrail "`ChatView(` appears in exactly one builder".
- `m2p.chat-dock-switches-conversation` — **[OK]** (101a67cde, #4817 closed): the ONE dock mount is a computed view re-rendered with a
  new `conversation` param on every sidebar selection, never remounted (no `.id(…)`) —
  `currentConversation`/`backendConversationId` are `@State`, seeded ONLY at first mount, so
  a sidebar-driven switch used to leave the PREVIOUS conversation showing (and sending into).
  Bridge fix, found while planning increment 5b: `.onChange(of: conversation?.id)` calls the
  EXISTING `switchConversation` (the same reset/reload the title menu's own switch already
  does, same `isConversationPinned` guard); `ResearchChatPane` needed a PARALLEL
  `.onChange(of: researchProject?.id)` (it always passes `conversation: nil`, so the first
  bridge never fires for it) calling a new `resetToFreshConversation()`, sharing one
  `resetComposerState()` helper with `switchConversation` so the two can never drift on what
  "looking at something else" resets. This is a BRIDGE, not the structural fix —
  `m2p.chat-single-mount` above (lifting the state out of `@State` entirely) remains
  increment 6's job. Pinned by
  `ChatViewBoundaryTests.testChatViewObservesConversationChangesAndBridgesToSwitchConversation`,
  `.testChatViewObservesResearchProjectChangesAndResetsToAFreshConversation`,
  `.testSwitchConversationAndResetToFreshConversationShareOneResetHelper` (source-scan — a
  live `@State`-mutation assertion needs a hosting harness this suite does not have, the same
  limitation this file's other `ChatView` tests already accept).
- `m2p.chat-scope-lives-in-both` — **[PROPOSED]**, renamed from `m2p.chat-scope-inspector-only`
  (creative director, 2026-09-18, supersedes it): chat scope lives in BOTH the Inspector's
  Sources tab (`ChatInspector`) AND the chat dock's own Sources view — the dock's Sources tab
  is NOT deleted. Pinned by a guardrail asserting BOTH mounts exist (the inverse of the old
  "exactly one call site outside its own file" rule).
- `m2p.comparison-is-panes-and-diff-lens` — **[PROPOSED]**, renamed from
  `m2p.comparison-folds-into-chat-compare` (creative director, 2026-09-18, supersedes it).
  Scope clarified 2026-09-18: `AppViewMode.comparison`/`ComparisonDetailView` retirement moved
  OUT of increment 4a into increment 4c — three sites still
  construct `.comparison` today, none touched by 4a. When it lands: `AppViewMode.comparison`
  and `ComparisonDetailView` are DELETED, but chat's Compare tab is NOT where comparison lives
  either. A "run with A and B" action leaves two sibling artifacts; the Compare workspace
  shows them in two Reader panes with a diff lens — comparison is about two
  prompts'/workflows' outputs, not a conversation. Pinned by a matrix row (no `.comparison`
  surface) + a guardrail that `ComparisonDetailView` does not appear in the app target + a
  Reader diff-lens test once the lens exists.
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
- `m2p.pane-toggles-everywhere` — **[OK]** (e59ba3d07, #4779 closed; Research still hides
  them until increment 5 stops it being a takeover): the toolbar's pane-visibility toggles
  (`ContentView+StateLayout.swift`'s `showsPaneToggles`) used to gate on `sidebarMode ==
  .library` alone, so they stayed hidden for `.chat` and, since increment 2, for `.workflows`
  too — even though both had a real Library + Preview + Reader shape with genuine content to
  toggle. Fixed as part of "4a-follow" (same delivery as
  `m2p.open-affordance-adds-missing-preview-pane` below, since the missing-Preview-pane
  affordance's toolbar counterpart was the same underlying gap): `showsPaneToggles` is now an
  EXHAUSTIVE per-`SidebarMode` switch (the `CompactShellPolicy.route` pattern) — `.library`,
  `.chat`, `.workflows`, `.automation`, `.activity` all show the toggles; only `.research`
  (still a bespoke takeover) hides them, retiring with increment 5. Pinned by
  `ToolbarTogglePolicyTests.testPaneTogglesShowForEveryPaneHostedModeHideOnlyForResearch` and
  `testPaneTogglesHiddenInCompactFlowForEveryMode` (every `SidebarMode` × `compactFlow`).
- `m2p.open-affordance-adds-missing-preview-pane` — **[OK]** (e59ba3d07): generalizes
  the creative director's workflow ruling ("an explicit Open affordance adds the pane; nothing
  moves automatically") to the five kinds increment 4a moved into Preview alongside the
  workflow canvas from increment 2. When a selection's Preview cell is `.workflowCanvas` or
  `.nodeDetail` and no Preview leaf is currently applied, the Library pane's content column
  shows an inline banner naming what is not shown, with one button that adds the pane through
  the existing `setPaneVisible(.canvas, true)` funnel — never an automatic layout change.
  Scoped to those two surfaces only; a plain document/chat/comparison selection with Preview
  hidden is the user's own layout choice, not a takeover this migration retires. Pinned by
  `PaneContentPlanTests.missingPreviewSurfaceFiresOnlyForNodeKindsWithoutAPreviewLeaf` (the
  pure predicate, every `AppViewMode` × `hasPreviewLeaf`) — no automated SwiftUI-render test
  yet asserting the banner actually mounts (a coverage gap, flagged, not silently claimed as
  pinned, same honesty precedent as `m2p.workflow-reader-is-run-log`).
- `m2p.reader-consults-the-plan` — **[OK]** (fb2829fd7, #4803 closed): the Reader pane must render `PaneContentPlan.plan(for: viewMode).reader`'s cell,
  not whatever `Document` happens to still be resolved from a previous selection.
  `ReadingPaneView` had no reference to `viewMode`/`AppViewMode` at all, so a
  schedule/trigger/chain/batches/automation/activity selection left every Reader tab (Page,
  Notes, Knowledge — none of them cleared or checked anything) showing the PREVIOUSLY selected
  document, never the matrix's own honest `.empty` reason. Fixed by a new
  `PaneContentPlan.Cell.readerPageRoute` gate ahead of the tab switch — see increment 4b-1
  above for the full mechanism. Pinned by
  `PaneContentPlanTests.readerPageRouteRecognizesTheNamedSurfacesAndUnmountsEverythingElse` (pure, every
  `PaneSurface` + `.empty`) — no automated SwiftUI-render test yet asserting the Reader actually
  mounts `PaneEmptyStateView` for a live schedule selection (a coverage gap, flagged, same
  honesty precedent as `m2p.workflow-reader-is-run-log`).
- `m2p.scroll-updates-page-focus-only` — **[OK]** a reader page signal must never
  disagree about how much of the window it may re-point: scrolling past a page (the viewport
  drifting) and clicking a page (an instruction) both move the shared page-focus cursor that
  drives the preview and inspector, but NEITHER ever re-roots `detailDocument` — the previewed/
  active document stays pinned to its container (the parent PDF/folder) so the WebKit
  transcript is never torn down and reloaded by a click or scroll meant to move within it.
  `ReaderPageSignal` (`ReaderPageActivationState.swift:37-62`) states this as a value
  (`movesPageFocus`/`movesBrowserSelection`/`rerootsPreviewedDocument`) rather than two
  hand-written branches, which is what makes the invariant assertable at all. Pinned:
  `ReaderPageActivationTests.neitherSignalRerootsThePreviewedDocument`,
  `.bothSignalsMovePageFocus`, `.bothSignalsMoveTheBrowserSelection`. The legacy issue asking
  for this decoupling is a verify-close candidate — the code and its own comments name that
  issue by number as the ruling this mechanism implements — flagged for the maintainer rather
  than closed here.
- `m2p.inspector-names-its-selection-scope` — **[GAP]** (#1762) the Inspector should visibly
  NAME the scope it's showing — Page / Folder / N Pages / Selection — not just silently render
  different content for each. Verified: `m2p.inspector-follows-selection` (above) proves the
  RIGHT CONTENT KIND mounts per selection, and `ContentView+StateDisplay.swift:158`'s
  `"\(browserSelection.count) items selected"` is an adjacent but DIFFERENT mechanism — a pane
  head / status-area count string, not the Inspector itself naming its own scope. No title or
  header was found anywhere under `Views/Inspector/` that reads "Page"/"Folder"/"N Pages"/
  "Selection" as the Inspector's own identity. Not built.
- `m2p.automation-run-history-in-reader` — **[OK]** (ba7871c09; → #4741 closed, the `automation`
  spec's own issue): a schedule/trigger/activity selection must show its run history in the
  Reader, not the honest-but-now-obsolete `.empty("A schedule has no reader view.")` (etc.) the
  matrix stated before this landed. Fixed by extracting `ScheduleDetailView`'s/
  `TriggerDetailView`'s run-history sections into `ScheduleRunHistoryView`/
  `TriggerRunHistoryView` (Activity needed no extraction — `ActivityLogView` already existed
  standalone) and mounting the SAME components from the Reader's new `.runHistory` route via
  `PaneContentPlan.ReaderSubject` — see increment 4b-2 above for the full mechanism, including
  the reload-on-identity-change fix and the environment-inheritance proof. Pinned by
  `PaneContentPlanTests.automationKindsLandOnTheRunHistoryReaderSurface` and
  `PaneContentPlanTests.readerSubjectFromNamesTheRightEntity` (pure, every `AppViewMode`
  including the nil sub-cases) — no automated SwiftUI-render test yet asserting the extracted
  components actually mount live (a coverage gap, flagged, same honesty precedent as
  `m2p.reader-consults-the-plan`).

### Legacy milestone fold — node reversibility across Library view modes

- `m2p.grouped-nodes-drill-consistently-across-view-modes` — **[GAP]** (#3699, redirected
  from the legacy "Library View - Column Browser & Columns" milestone while folding
  `library-view-modes.md`'s pass 2) a GROUP/STACK node (an already-closed earlier feature)
  should show as one item that expands/drills into its members, and a SPLIT child (also an
  already-closed earlier feature) should be reachable under its source, consistently across
  Icon, List, and Columns — with ungroup/unsplit staying
  reversible in every one of them. This is the node model's own reversibility guarantee
  applying across view modes, not a per-mode display question, which is why it lives here
  rather than in `library-view-modes.md`. Not verified as built.

### Node-row identity — a child row promotes ITS OWN node, not a composite id

- `m2p.page-artifact-note-rows-promote-their-own-node` — **[PARTIAL]** (fixed 82ae96b9b; #4862
  stays open for the maintainer to confirm on screen) a page, artifact, or note child row in
  the browser selection promotes to ITS OWN node — never falls through to the generic
  document-promotion path carrying a composite outline id, the same defect class
  `kg.entity.focus-uses-the-bare-id` (`kg-entity-inspector.md`) fixed for entity/claim rows.
  Fixed: a page row now resolves and promotes its own page Document by its bare item id
  (pages ARE real Documents, nested only for disclosure); artifact and note rows are a safe
  NO-OP at this handler — they already have a correct, richer resolution elsewhere
  (`LibraryView+TableView.swift`'s own `.onChange(of: selection)`, which ContentView has no
  access to reconstruct), so the fix is to stop them reaching the generic promotion path with
  a composite id, not to re-derive their real handling here. **Found in the same audit, not
  fixed here**: the identical composite-id class still reaches the workflow editor's crumbs,
  the Reader's crumb drag payload and new-window paths, three artifact-lens sites, a few claim
  card and PDF-toolbar sites, and a table helper that splits a node id on its FIRST colon
  (rather than the last, right-to-left split `LibraryOutlineNode.parse(nodeId:)` uses
  elsewhere) — named honestly as remaining, not implied closed. Pinned:
  `EntityClaimSelectionClassifyTests.pageRowPromotesItsOwnPageViaBareId`,
  `.artifactAndNoteRowsAreASafeNoOp` (file
  `fichero/Tests/Unit/general/Views/Shell/EntityClaimSelectionClassifyTests.swift`, suite
  `EntityClaimSelectionClassifyTests`).

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
  Files: `Nav`, `Detail`, `Plan`, `ContentView+StatePreview.swift`. Deletes: the "Select a
  Workflow" placeholder (`Nav:296-304`). Needs the no-collapse ruling below (open question 2)
  or selecting a workflow in a Browse workspace with no Preview leaf shows nothing. Test:
  `m2p.workflow-canvas-in-preview`, `m2p.library-is-always-navigator` (drop `WorkflowEditor(`).
  (`showsPaneToggles` did NOT stop gating on `sidebarMode == .library` here as originally
  planned — that gap became #4779 and was fixed later, in "4a-follow," alongside
  `m2p.open-affordance-adds-missing-preview-pane`; see that behavior's entry.)
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
  standing creative-director ruling (2026-06-25 → #2593, → #2614) requires it stay visible; it was
  NOT part of the review's original delete list and surfaced only once the deletion exposed it
  had no other caller. Now its own file/window, reached from the Knowledge menu. **Persistence:**
  a window saved with `sidebarMode == "knowledgeGraph"` restores to `.library` — routed through
  `SidebarMode.restored(from:)` (not `RawRepresentable.init(rawValue:)`'s unproven default
  fallback), landed in increment 3a ahead of the deletion itself. Test:
  `m2p.kg-graph-retires-as-library-takeover` + `SidebarModeRestoreTests` (the restore table).
- **4a. Automation / schedule / trigger / chain / batches / activity / batch → Preview-pane
  node detail — DONE (9128ecdee, 2026-09-18).** Comparison is OUT of this increment's
  scope — CD 2026-09-18 moved its retirement to increment 4c below
  (§the `.comparison` matrix row, `m2p.comparison-is-panes-and-diff-lens`). Same move as
  increment 2, row by row. Deleted `AppViewMode.batch` (`SelH` already redirected to
  `.activity`), the `.automation` placeholder arm, the `.batch` construction sites; MOVED the
  "Create Chain" empty state (`Nav:313-318`) to the Preview rendition rather than deleting it.
  Deleted `ActivityWindowLauncherView` (zero remaining callers or bare references, verified by
  type defined in file, not textual constructor grep — the GraphSimulation lesson from
  increment 3). Files: `Nav`, `Detail`, `Plan`, `Models/SidebarViewTypes.swift`, `SelH`,
  `ContentView+Persistence.swift`, `ContentView+StateDisplay.swift`,
  `ContentView+StateSelection.swift`, `ShellLayoutPolicy.swift`,
  `Views/Activity/ActivityViewHelpers.swift`. **Persistence:** `restoreViewMode`
  (`ContentView+Persistence.swift:60-100`) keeps accepting the retired `"batch"` string
  alongside `"batches"` — a session saved before the deletion still restores to `.activity`.
  Test: `m2p.automation-nodes-in-preview`,
  `PaneContentPlanTests.nodeDetailModesLandInThePreviewSlot`,
  `LibraryPaneNeverMountsModeSurfaceTests` (allowlist shrunk to `ResearchWorkspaceView(`/
  `ComparisonDetailView(`; `deletedBareIdentifiers` gained `ActivityWindowLauncherView`),
  `ContentViewPersistenceTests.testRetiredBatchStringStillRestoresToActivity`.
- **4b-1. The Reader consults the plan — DONE (2026-09-18, fb2829fd7), fixes the live
  stale-document bug #4803.** Discovered planning 4b: `ReadingPaneView` had NO reference to
  `viewMode`/`AppViewMode` anywhere — the whole Reader routed off a resolved `Document`
  (`effectiveDocument`/`liveDocument`/`pinnedDocument`), not the selection's plan cell.
  `.workflow` only reached its run-log rendition because workflow DEFINITIONS are themselves
  library Documents (`Document.isWorkflowNode`, `prototypeKey == "workflow"`) that ordinary
  document-selection machinery resolves — the matrix's `reader` column had been decorative since
  increment 1, never actually consulted at runtime. Confirmed LIVE BUG (#4803): none of the
  automation-family selection handlers (`.chain`/`.batches`/`.automation`/`.schedule`/
  `.trigger`/`.activity`) clear `detailDocument` (`handleViewModeChange`/
  `MainContentModifiers+ViewMode.swift` only branches on `.workflow`/`.library`), so
  `readerDocument` (`ContentView+DetailLayout.swift:249-253`) kept returning whatever document
  was last open — selecting a schedule left the Reader showing the PREVIOUSLY selected
  document's transcript AND notes AND knowledge tab, not an honest empty state, on every tab
  (fix-then-sweep-for-siblings: the Page tab was the reported symptom, but Notes/Knowledge share
  the identical `effectiveDocument`-driven fallback and the same stale risk). This increment
  fixes it as a direct side effect, and deliberately does NOT add a second mechanism that clears
  `detailDocument` — the plan is the one authority, and clearing it would break "Back to the
  document" navigation. Mechanism: `ReadingPaneView` gains one new defaulted property,
  `var readerCell: PaneContentPlan.Cell = .surface(.documentReader)` (default keeps every
  existing call site — there is exactly one production one,
  `ContentView+DetailLayout.swift:286`, inside `widescreenReadingPaneBody`, which already has
  `viewMode` in scope — and every preview compiling unchanged), set there to
  `PaneContentPlan.plan(for: viewMode).reader`. A new pure routing function,
  `PaneContentPlan.Cell.readerPageRoute -> ReaderPageRoute` (`.documentDriven` for
  `.surface(.documentReader)`/`.surface(.workflowRecipe)`, `.empty(String)` passthrough,
  `.unmounted(PaneSurface)` for anything else — an honest state that NAMES the surface, never a
  blank, rather than silently falling into the document-driven chain), gates
  `ReadingPaneView+Tabs.swift`'s `readerTabContent` — ONE gate ahead of the existing
  Page/Knowledge/Notes switch, the smaller and more honest change versus filtering the tab
  switcher's lens menu itself: `.documentDriven` reaches the EXISTING Page/Knowledge/Notes split
  byte-for-byte unchanged (never touches `doc.isWorkflowNode`/`loadReaderWorkflow()`),
  `.empty(reason)` renders `PaneEmptyStateView` with the matrix's own reason string on EVERY tab
  (today's `.empty` reasons are computed but were never shown to anyone — this makes them real),
  `.unmounted` is 4b-1's safety net (nothing produces it yet; 4b-2's `.runHistory` will be the
  first, rendered as `"The Reader has no <surface> rendition yet."`). Files: `Plan` (the routing
  type + function), `ReadingPaneView.swift` (the new property), `ReadingPaneView+Tabs.swift` (the
  gate), `Detail` (the one call site). Test: `m2p.reader-consults-the-plan`,
  `PaneContentPlanTests.readerPageRouteRecognizesTheNamedSurfacesAndUnmountsEverythingElse` (every
  `PaneSurface` + a representative `.empty`, pure).
  **Lesson (added post-gate, 2026-09-18):** making code start OBEYING a table that was
  previously decoration turns every WRONG row into an immediate regression — the `.chat` row
  said `reader: .empty("A conversation has no reader view.")`, which was false but harmless
  while nothing read it; 4b-1 would have blanked the Reader for every chat user the moment it
  shipped. Caught and fixed before landing, pinned by `PaneContentPlanTests.
  chatKeepsADocumentDrivenReader`; the matrix row above corrected to match. The checklist now
  requires: before a change makes any table/matrix cell load-bearing for the first time, audit
  every row against today's REAL behavior, not just the row being directly touched. A parallel
  audit found `entitySelection`'s reader cell (`Plan:123`, `"An entity list has no reader
  view."`) is similarly inaccurate once a SPECIFIC entity/claim row is focused
  (`LibraryView+TableView.swift:288-293` sets `detailDocument` to that row's real source
  document) — currently harmless because NO production call site ever passes
  `entitySelection: true` to `PaneContentPlan.plan(for:)` (only three call sites exist, all
  default it), so this is a `[GAP]`, flagged for whoever eventually wires it, not a live
  regression from 4b-1. `.comparison`'s `.empty("A comparison has no reader view.")` was
  checked and confirmed accurate — no `.comparison` selection site writes `detailDocument`.
- **4b-2. `.runHistory` — DONE (2026-09-18, ba7871c09), #4741.** Extracted
  `ScheduleDetailView.runHistorySection`/`runRow`/`runStatusColor`/`loadRuns` verbatim into a
  new `ScheduleRunHistoryView(scheduleId: String)`, and `TriggerDetailView.
  executionHistorySection`/`executionRow`/`executionStatusColor`/`loadExecutions` (formerly
  split across `TriggerDetailView+ExecutionHistory.swift`, now deleted — its only two members
  moved wholesale — and `TriggerDetailView+Helpers.swift`) verbatim into a new
  `TriggerRunHistoryView(triggerId: String)` — no logic rewrite, no restyle, only
  `schedule.scheduleId`/`trigger.triggerId` became plain `String` params. Activity needed NO
  extraction: `ActivityDetailView`'s `.log` tab already mounted a standalone
  `ActivityLogView(selectedRun: SelectedActivityRun)` (`Views/Activity/ActivityLogView.swift`)
  with its own load, its own live/completed branching, and correctly-optional environment reads
  already — the Reader's `.runHistory` branch mounts the SAME component a second time. One
  renderer per kind, two mounts (Preview's detail view unchanged; the Reader is the new mount),
  zero duplication. Payload: `.runHistory` stays a plain `PaneSurface` case (Swift cannot
  synthesize `CaseIterable.allCases` for a case with an associated value); a second, separately
  computed value carries the identity — `PaneContentPlan.ReaderSubject` (`.schedule(scheduleId:
  String)`, `.trigger(triggerId: String)`, `.activityRun(SelectedActivityRun)` — the SMALLEST
  thing each component needs; Schedule/Trigger only read an id, so carrying the whole
  `ScheduleInfo`/`TriggerInfo` would make the Reader re-evaluate on every unrelated field change
  and couple it to the detail model; Activity's component genuinely needs the whole struct).
  `ReaderSubject.from(_ viewMode: AppViewMode) -> ReaderSubject?` is exhaustive (no `default`) on
  `ReadingPaneView`'s new `readerSubject` property, computed by the same host as `readerCell`,
  from the same `viewMode`. Nothing-selected (`.schedule(nil)`/`.trigger(nil)`/`.activity(nil)`):
  reuses 4a's own answer to the identical question for Preview — the reader CELL stays the
  constant `.surface(.runHistory)` regardless of nil; the nil/non-nil distinction is handled by
  `readerSubject` being nil, at the Reader's dispatcher, not the matrix. The per-kind honest
  reason for that nil case stays SPECIFIC ("Select a schedule/trigger/run to see its ... run
  history.") via a second small property, `AppViewMode.runHistoryEmptyReason`, since collapsing
  to a bare `ReaderSubject?` loses which kind it was. Reload-on-identity-change (the classic
  extraction-into-a-long-lived-host bug — the Reader pane persists across selections, unlike the
  Preview detail view SwiftUI rebuilds per selection): `ScheduleRunHistoryView`/
  `TriggerRunHistoryView` key their load on `.task(id: scheduleId)`/`.task(id: triggerId)` and
  clear their rows before each fetch; the Reader's dispatcher ALSO mounts every kind with
  `.id(subject)`, forcing a fresh identity on any change. Checked `ActivityLogView`'s own
  `.task(id: selectedRun.threadId...)` for the same defect — it already keys correctly and its
  `isLoading` branch is checked BEFORE its `workflowRun` branch, so a stale run's content is
  never shown mid-fetch; no fix needed there. One wrinkle NOT a pure verbatim move: extracting
  `loadExecutions()` out from under `TriggerDetailView`'s existing "Refresh" button (Schedule has
  no equivalent button) broke its direct call; fixed with a `runHistoryRefreshToken: UUID`
  `@State` that the button bumps and `TriggerRunHistoryView` is `.id()`-mounted on, reusing the
  same forced-remount mechanism rather than adding a second refresh API to the shared component.
  Environment safety: `WorkflowExecutionObserver` is part of `WindowEnvironmentModifier`,
  re-injected at every pane leaf (`PaneSpec.swift:313`, the PROVEN-inheriting boundary, distinct
  from Toolbar/Inspector which are not); `WorkflowExecutionStore` is injected at
  `LibraryWorkspaceRoot.swift:103`, the app-wide root every pane nests under — both reliably
  reach a Reader-mounted view. `ActivityLogView` already declared them correctly
  (`WorkflowExecutionObserver` non-optional, matching `WorkflowOutputLog`'s proven-safe
  precedent; `WorkflowExecutionStore` already optional) and neither line was touched.
  `EnvironmentOptionalObservableGuardrailTests.scannedDirectories` is `["Views/Shell/Toolbar",
  "Views/Inspector", "Views/Workflow/Inspector"]` ONLY — it does NOT cover `Views/Activity/` or
  `Views/Library/Automation/`, so it would not have caught a violation here either way; noted for
  #4774, not widened in this delivery. **Open question for the creative director** (not decided
  here): a schedule/trigger/run now shows its history in BOTH the Preview detail view and the
  Reader — kept both for this delivery (the Reader pane may be closed), whether the Preview
  detail view should drop its own history section once the Reader has it is undecided. Files:
  `Plan`, `ReadingPaneView.swift`, `ReadingPaneView+Tabs.swift`, `Detail`, `ScheduleDetailView.
  swift`, `ScheduleRunHistoryView.swift` (new), `TriggerDetailView.swift`,
  `TriggerDetailView+Helpers.swift`, `TriggerRunHistoryView.swift` (new; deleted
  `TriggerDetailView+ExecutionHistory.swift`). Test: `m2p.automation-run-history-in-reader`,
  `PaneContentPlanTests.automationKindsLandOnTheRunHistoryReaderSurface`,
  `PaneContentPlanTests.readerSubjectFromNamesTheRightEntity` — no automated SwiftUI-render test
  yet asserting the Reader actually mounts these components live (coverage gap, flagged, same
  honesty precedent as `m2p.workflow-reader-is-run-log`/`m2p.reader-consults-the-plan`).
- **4c. Comparison + diff lens (not started).** `AppViewMode.comparison` and
  `ComparisonDetailView` are DELETED; comparison becomes two sibling artifacts shown as two
  Reader panes with a diff lens (not a mode, not chat's Compare tab; see
  `m2p.comparison-is-panes-and-diff-lens`) — the diff-lens UI itself is a separate,
  not-yet-scoped follow-up, this increment only removes the retired mode/view and adds the
  matrix row. Split out of the original increment 4 (CD 2026-09-18: three sites still
  construct `.comparison` today, none touched by 4a). Files: `Nav`, `Detail`, `Plan`,
  `Models/SidebarViewTypes.swift`. **Persistence:** `restoreViewMode` keeps accepting the
  retired `"comparison"` string exactly as it already does for `"search"`. Test:
  `m2p.comparison-is-panes-and-diff-lens` + a restore-table test.
- **5a. Workspaces are library folders — DONE (11368be12), #4812 closed.**
  Agent workspaces (`workspace_kind=agent` folder Documents) are already ordinary library
  `Document`s (`isWorkspace: Bool`) — the design decided NEITHER a new sidebar bucket NOR a
  labeled section: a workspace already appears in the ordinary tree wherever its parent
  folder is visible, so a second, flat "all my workspaces" list (bucket or section) would
  show the same folder TWICE with the SAME id — duplicate identity in a SwiftUI `ForEach`
  (undefined selection/diffing, the row-resurrection class of bug this sidebar has already
  fought). A first attempt at the bucket approach was built, then reverted for exactly this
  reason before landing.
  **Deletion:** removed the redundant SECOND create path — `ResearchProjectListView`'s
  `workspacesSection`, `workspaceRow(_:)`, `newWorkspaceForm`, the "New Workspace" toolbar
  button, and their `@State` (`showingNewWorkspace`, `newWorkspaceName`), plus the now-unused
  `@Environment(DocumentStore.self)` and its `.task`'s `loadWorkspaces()` call.
  `SidebarCreationHandlers.createNewWorkspace()` was ALREADY wired (`itemRegistry.
  createWorkspace = createNewWorkspace`, `SidebarObservers.swift:202`) into the real creation
  menu (`ItemTypeRegistry.swift`, id `"workspace"`) — the form was dead weight, confirmed by
  caller-evidence grep before deleting. `ResearchProjectListView`'s project list is
  UNTOUCHED — no replacement until 5b.
  **Selection fixed:** `routeDocumentSelection`'s `if doc.isWorkspace` branch
  (`SidebarView+SelectionHandling.swift`) is DELETED — `git log -S'isWorkspace'` traced it to
  229f76368 ("selecting a workspace routes to the Research surface"); that need is 5b/5c's (a
  research PROJECT's own chat/tasks/browser rendition — `ResearchProject`, a separate model
  with no folder/Document link at all), not this document row's. A workspace document now
  falls through to the SAME generic library branch every other folder gets
  (`sidebarMode = .library`, `viewMode = .library(doc)`). The function mixes async alias
  resolution with sync branches — not a pure function today — so this is pinned by a
  source-scan guard, not an extracted pure routing function.
  **Placement fixed, reusing the folder path, not a copy:** `DocumentStore.createWorkspace`
  gained a `parentId: String? = nil` (`DocumentStore+CRUD.swift`), threaded straight into the
  SAME `createFolder(name:parentId:)` every folder already uses — no separate server-side
  wiring needed, the workspace marker PATCH is keyed on the created folder's own id regardless
  of where it landed. `createNewWorkspace()` computes `parentId` with the EXACT SAME
  selected-folder check `handleCreateNewFolder()` uses (nest into the selected folder; library
  root as the fallback — → sidebar-crud's `create.folder.lands-under-context`, itself
  `[PARTIAL]` today per that spec: the naming dialog and parent-reveal gaps it already has are
  INHERITED here, not re-litigated), then selects the result WITHOUT forcing `sidebarMode`
  (matching `createFolder(_:)`'s own select-only completion) — it browses like any folder now.
  **Not fixed, reported per instruction, do not delete without confirming:**
  `DocumentStore.workspaces`/`loadWorkspaces()` have zero PRODUCTION callers after this
  delivery, but TWO tests pin `workspaces` as one of several arrays the store's granular
  `apply(document.deleted)`/`liveDocument(id:)` mechanisms must keep in sync —
  `DocumentStoreLiveResolutionTests.liveDocumentReadsAllContainers` and
  `ObservableDomainStoreTests.testApplyDeletedRemovesRowsInPlaceAcrossListsAndCache` — neither
  is about the deleted Research UI; both exercise `workspaces` generically alongside
  `collections`/`currentDocuments`/`childrenCache`. Deleting the property would need editing
  both tests too; left in place pending a decision. Files: `SidebarView+SelectionHandling.
  swift`, `DocumentStore+CRUD.swift`, `SidebarCreationHandlers.swift`,
  `ResearchProjectListView.swift`. Test: `m2p.research-workspaces-are-library-folders`,
  `SidebarWorkspaceNodeTests.testWorkspaceSelectionNoLongerDivertsToResearch`,
  `.testCreateNewWorkspaceReusesFolderPlacementAndSelects`, `.testRegistryWiringIncludesWorkspace`,
  `.testResearchProjectListViewHasNoWorkspaceUI` (all source-scan — the dedicated,
  pre-existing workspace-node test file this delivery updated rather than orphaned).
- **5b. A research project is a sidebar node (planned, not started).**

  **(1) `SidebarItem.ItemType` + id namespace, checked for disjointness first.** A new
  `case researchProject(ResearchProject)`. Id prefix `"research:\(project.id)"` — grepped
  every existing prefix (`SidebarItem.swift`/`+MoreFactories.swift`): `doc:`, `search:`,
  `workflow:`, `chat:`, `folder:`, `library:`, `chain:`, `comparison:`, `schedule:`,
  `trigger:`, `batch:`, `activity:`, `structure:` — none is `research:` or a prefix of it, so
  no collision. Disjointness from `documentItems` holds structurally, not just by
  convention: a `ResearchProject` has NO `Document`/folder id at all (`id, name, description,
  status, libraryDestinationFolderId, createdAt, updatedAt` — `libraryDestinationFolderId` is
  a DIFFERENT id, the folder a project's outputs save into, not the project's own identity),
  so a `researchProjectItems` bucket can never contain a row `documentItems` also contains —
  unlike 5a's workspace bucket, which failed disjointness for exactly this reason. Joins the
  ONE flat list (`flattenedLibraryItems`) as a new bucket, gated on `isResearchEnabled`,
  sourced from `researchService.projects` (already `@Observable`) the same way
  chain/schedule/trigger read their own live `@State` sources — this is the bucket shape 5a's
  reversion ruled out for workspaces, but IS correct here because there is no duplicate-id
  risk to trigger the same `ForEach` bug.

  **(2) `AppViewMode.research(ResearchProject?)` — every switch it breaks, verified by
  reading each file, not assumed:**
  EXHAUSTIVE `switch` over `AppViewMode` (compiler forces a decision, cannot be missed):
  `SidebarViewTypes.swift:24` (`category`), `:41` (`logDescription`); `ShellLayoutPolicy.
  swift:163` (`CompactShellPolicy.route`); `PaneContentPlan.swift` (`stablePanePlan`,
  `ReaderSubject.from(_:)`, `runHistoryEmptyReason`); `ContentView+Persistence.swift:125`
  (`serializeViewMode`); `Nav`'s `contentView` (the main router); `ContentView+StateDisplay.
  swift:20`/`:117` (`toolbarTitle`/`toolbarIcon`); `ContentView+StateSelection.swift:87`
  (`showNavigationToolbar`); `Detail`'s `inspectorView` and the compact-only `previewView`
  grouped switches.
  NOT exhaustive — will NOT fail to compile, so a manual pass is the only thing that catches
  these, and missing one is a SILENT gap, the more dangerous class:
  `ContentView+Persistence.swift:268` (`viewModeLostItsItem`) has a `default: return false` —
  a lost research-project selection would silently never register as "lost its item" unless
  a `.research` case is added deliberately. `ViewModeNormalization.swift`'s
  `defaultViewMode`/`preservesExistingSelection` switch on `SidebarMode` (which ALREADY has a
  `.research` case, unaffected by adding `AppViewMode.research`) — their EXISTING `.research`
  arms (lines 38, 81) currently return `.library(nil)` / `false`, a pre-5b workaround
  ("No dedicated AppViewMode case for this takeover mode" — that comment becomes false once
  5b lands) that must be rewritten to the `.workflows`-style pattern
  (`.research → .research(nil)` default, `.research(let selected) → selected != nil`
  preservation) — nothing forces this edit, it must be done deliberately or the Chat-Scope-
  leak class of bug this file exists to prevent reopens for Research specifically.
  `Detail`'s `widescreenCanvasPaneContent` is an `if case` CHAIN, not a switch — also not
  exhaustive-enforced, needs its own new branch. `ContentView+StateLayout.swift`'s
  `showsPaneToggles` switches `SidebarMode` (already has `.research`, currently `false`) —
  flip to `true` once Research is pane-hosted, matching 4a-follow's fix for the other modes.
  `SidebarItem.ItemType` gains its OWN exhaustive-switch fan-out from (1)'s new case —
  confirmed `SidebarActions.swift`'s `performDeleteAction` (exhaustive, will not compile
  without a `.researchProject` arm); context-menu and row-icon switches almost certainly
  also exhaustive over `ItemType` (`SidebarItemContextMenu.swift`,
  `SidebarItemRow+Presentation(+Body).swift`) but not individually verified here — inventory
  precisely at implementation time, the same GraphSimulation-lesson discipline.
  **Matrix row, audited against real wanted behavior first (the chat-row lesson from
  4b-1), not assumed:** Library browser | Preview = document preview (or `PaneSurface.
  webBrowser` once 5c lands and no document is ALSO selected — the SAME `.chat`-shaped cell,
  branching only on whether a document is present, matching `.chat`'s own `document preview`
  cell today) | Reader = document-driven (`.surface(.documentReader)`, matching `.chat`'s
  audited fix in 4b-1 — a research project keeps its documents readable beside it, same
  reasoning) | Inspector = `.surface(.chatScope)`, matching `.chat`'s row exactly (Sources ·
  Plan · Knowledge · Compare — Plan renders `ResearchTasksPane(project:)` since
  `ChatView.swift:221-222` already does this whenever `researchProject` is set).

  **(3) Selection + the chat dock's seam.** Selecting a `.researchProject` row sets
  `sidebarMode = .library` (matching 5a's fix — a research project is browsed like a
  library node, not a takeover) and `viewMode = .research(project)`. The chat dock
  (`PaneSpec.swift`'s `chatSurface`) learns WHICH project via a value computed from
  `viewMode` at the SAME host that computes `ReaderSubject`/`readerCell`
  (`ContentView+DetailLayout.swift`) — the smallest seam, one more small pure function
  alongside `ReaderSubject.from(_:)`, not a new mechanism. **Verified, file:line, a REAL
  PRE-EXISTING bug independent of 5b, must be filed regardless:** the chat dock does NOT
  safely re-scope across selections today. `chatSurface` (`PaneSpec.swift:412-422`) is a
  computed `@ViewBuilder var`, re-evaluated every render with `ChatMount.conversation(for:
  viewMode)` — but `ChatView`'s `currentConversation`/`backendConversationId` are `@State`,
  seeded ONLY once at first mount (`ChatView.swift:114`:
  `self._currentConversation = State(initialValue: conversation ?? Conversation())`), and
  grepped `ChatView.swift` for `onChange(of:`/`.id(` — ZERO hits, confirmed. The mount site
  (`ContentView+SidebarLayout.swift:57`) has no `.id()` either. So selecting conversation B
  while conversation A is the dock's current mount does NOT reset `@State` — the SAME
  identity persists, only the `conversation` init param changes, which `@State`'s
  `initialValue` ignores after first mount. `ResearchChatPane.swift`'s own
  `ChatView(conversation: nil, ...)` construction has the identical gap. 5b's fix for
  RESEARCH selection specifically is `.id(project?.id)` on the dock mount (the same
  forced-remount technique 4b-2 used); the GENERAL conversation-to-conversation case is
  filed as its own bug regardless of 5b's fate.

  **(4) Create / rename / delete — reuse the sidebar's existing machinery, not rebuilt.**
  Today, `ResearchProjectListView` has `newProjectForm` (`researchService.createProject(
  name:)`) and delete (`confirmDelete`/`deleteProjects` → `researchService.deleteProject(
  id:)`), both bespoke, both in that one view. Maps to: creation → a new `ItemTypeRegistry`
  entry (`"research"` id, AI category, matching `"workspace"`'s shape) wired via
  `SidebarObservers.swift` to a new `SidebarCreationHandlers.createNewResearchProject()`
  (immediate creation, no dialog, same shape as `createNewWorkspace()` post-5a — no name
  dialog to reuse, since `ResearchProject` has no folder-creation-style Finder-semantics
  placement question at all, it is not a Document); delete → `SidebarActions.
  performDeleteAction`'s new `.researchProject` arm calling `researchService.
  deleteProject(id:)`, replacing the bespoke `confirmDelete`/`deleteProjects`/
  `projectsToDelete`/`showingDeleteConfirm` machinery in `ResearchProjectListView` with the
  sidebar's existing confirm-delete flow (the same seam every other node kind's delete
  already uses) — no rename affordance exists today for a `ResearchProject` (no `renameXxx`
  found for any kind in `SidebarActions.swift`, so this is not a regression, just not adding
  one).

  **(5) What 5b deletes vs. what waits for 5c.** Deletes: `ResearchProjectListView`'s
  `projectList`/`projectRow(_:)`/`newProjectForm`/delete machinery and their `@State`.
  Survives into 5c: the FILE `ResearchProjectListView.swift` itself (5c's job, once nothing
  mounts it — the `sidebarMode == .research` intercept in `Nav` dies with 5c, not 5b,
  since 5b only changes what a PROJECT ROW selection does, not the whole intercept — needs
  confirming at implementation time whether anything else still reaches that intercept once
  5b lands, or whether 5b can retire it early). `ResearchWorkspaceView.swift` — untouched by
  5b, 5c's delete.

  **(6) Tests + behavior ids.** `m2p.research-is-sidebar-node` — [PROPOSED], flips once
  built. Pure: id-namespace disjointness (a table of every existing prefix + `research:`,
  asserting no collision — mirrors 5a's namespace check but as an actual test); the new
  `ReaderSubject`-sibling function mapping `viewMode` → `ResearchProject?` for the chat dock,
  every `AppViewMode` including nil sub-cases (mirrors `ReaderSubjectFromNamesTheRightEntity`
  form); matrix row assertions in `PaneContentPlanTests`. Source-scan: the retitled
  `ViewModeNormalization` `.research` arms no longer return `.library(nil)`/`false`
  unconditionally; `SidebarActions.performDeleteAction` has a `.researchProject` arm; the
  chat dock mount carries `.id(`. A NEW, separate bug report (not this spec, not gated on
  5b): the chat-dock conversation-switching staleness — needs its own issue, its own test
  once filed.

  **(7) Open questions for you.** (a) Confirm `.id(project?.id)` is the right immediate fix
  for the dock's research-scoping, vs. holding it for increment 6's proper state-lifting (a
  temporary patch on code increment 6 will later rewrite). (b) Whether `researchProject`
  selection should ALSO clear the dock back to no-project when navigating away (today
  nothing resets `researchProject` back to nil on deselect — same `@State`-seeded-once class
  of gap). (c) Whether the general chat-dock staleness bug (found in (3)) should block 5b or
  ship as a parallel, separately-filed fix — I lean parallel, since 5b's own `.id()` fix
  sidesteps it FOR RESEARCH specifically without needing the general fix first, but flagging
  since you may want them landed together. Files: `Nav`, `ResearchProjectListView.swift`,
  `Models/SidebarViewTypes.swift`, `SelH`, `ContentView+Persistence.swift`,
  `ViewModeNormalization.swift`, `ContentView+StateLayout.swift`, `ContentView+StateDisplay.
  swift`, `ContentView+StateSelection.swift`, `Detail`, `Plan`, `ShellLayoutPolicy.swift`,
  `SidebarActions.swift`, `SidebarCreationHandlers.swift`, `SidebarObservers.swift`,
  `Models/ItemTypeRegistry.swift`, sidebar section files. Test: `m2p.research-is-sidebar-node`.
- **5c. The browser is a Source rendition — DECIDED (creative-director ruling,
  2026-09-18), design not yet built.** The embedded browser lives INSIDE the Source/Preview
  pane — no browser pane kind, no tab strip of its own — as `PaneSurface.webBrowser` when a
  research project is selected and no document is. `ResearchBrowserPane(project:)` mounts in
  the Preview leaf AS-IS (verified: it needs only `project: ResearchProject` +
  `@Environment(ResearchService.self)`, is fully self-contained — its own toolbar, its own
  `FicheroWebView`, its own save action — and fills `.frame(maxWidth: .infinity, maxHeight:
  .infinity)` internally, the same shape every other 4a node-detail view already gets wrapped
  in). `ResearchService` is already part of `WindowEnvironmentModifier`'s re-injected set, so
  it reliably reaches the Preview pane leaf the same way `WorkflowExecutionObserver`/
  `WorkflowExecutionStore` do (§4b-2's inheritance proof).
  **The ruling draws a hard line this bullet's design must keep, not blur:** SCRATCH
  browsing (finding a source — a search engine, a catalogue, any page visited while looking)
  is navigation, never a node, nothing persisted beyond a session-only back/forward trail —
  `m2p.scratch-browsing-persists-nothing`. A SAVED source is the only thing that becomes a
  node, and only via an explicit save through the one audited action layer: either the page
  captured as a native `.webarchive` (URL + capture time), or — preferred where the page
  supports it — the EXTRACTED output saved as the artifact, with the page recorded as its
  provenance, not the page itself — `m2p.saving-a-source-makes-a-node`. The agent's tools
  reach for catalogue/repository APIs first; the browser is the fallback for API-less sites
  and the surface the human watches the agent work on. **Grounded gap found while planning:**
  `FicheroWebView` (`Views/Components/FicheroWebView.swift:25-30`) configures its `WKWebView`
  with a bare `WKWebViewConfiguration()` — it never sets `.websiteDataStore = .nonPersistent()`,
  so cookies/cache/localStorage persist to WebKit's default on-disk store across launches
  today. Whether that is wrong is an OPEN question for the creative director (#4810): pages
  being scratch is not the same as logins being scratch — a fully ephemeral store logs the
  researcher out of every library proxy, archive and catalogue on each launch. Options recorded
  on the issue: persistent cookies only; fully ephemeral; one data store per research project;
  possibly stricter for agent-driven browsing than for human browsing. No back/forward trail exists in the UI at all today —
  `ResearchBrowserPane`'s `toolbar` (`ResearchBrowserPane.swift:37-56`) has a URL field and a
  Save button only, no history list, no back/forward buttons — `urlString` is a single
  current-URL `@State`, not a trail. The trail needs building, not just re-routing.
  `ResearchWorkspaceView` and `ResearchProjectListView` finish deleting here (nothing left
  mounting either); `allowedTakeovers` drops `ResearchWorkspaceView(`; `showsPaneToggles`
  (`ContentView+StateLayout.swift`) returns true for `.research` (its exhaustive switch
  already needs updating — see 4a-follow's `m2p.pane-toggles-everywhere`). Files: `Nav`,
  `Detail`, `Plan`, `ContentView+StateLayout.swift`, `LibraryPaneNeverMountsModeSurfaceTests`,
  `FicheroWebView.swift` (data-store policy, once #4810 is ruled),
  `ResearchBrowserPane.swift` (back/forward trail + the save-action split), deletes
  `ResearchWorkspaceView.swift`, `ResearchProjectListView.swift`. Test:
  `m2p.research-is-sidebar-node` (extended), `m2p.browser-is-a-source-rendition`,
  `m2p.scratch-browsing-persists-nothing`, `m2p.saving-a-source-makes-a-node`, a guardrail
  dropping `ResearchWorkspaceView(`.
- **6. Chat movable as a pane.** Lift `ChatView`'s `@State currentConversation` /
  `backendConversationId` (`ChatView.swift:61-66`) into the per-window model; add
  `ChatPlacement.resolve(paneListHasChatLeaf:showChatPane:) -> .dock | .pane(leafID) |
  .hidden`; replace the `.chat` placeholder (`PaneSpec:167-179`). The Sources tab vs.
  `ChatInspector` do NOT de-duplicate (CD 2026-09-18 supersedes the earlier "Inspector only"
  plan: chat scope lives in BOTH places — see `m2p.chat-scope-lives-in-both`). Comparison is
  NOT this increment's concern either (CD 2026-09-18: it retires as panes + a diff lens in its
  increment 4c — never folded into chat's Compare tab — see
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
   panes with a diff lens. `ComparisonDetailView` and `AppViewMode.comparison` retire — but
   chat's Compare tab is NOT their replacement either; comparison is about two prompts' or two
   workflows' outputs, not a conversation. Supersedes the review's "folds into chat's Compare
   tab" recommendation — retitled to `m2p.comparison-is-panes-and-diff-lens` below. Scope
   clarified 2026-09-18: retirement moved OUT of increment 4a into increment 4c (ahead of
   increment 6) — three sites still construct `.comparison`
   today. Loove stays its own window (a diagnostic matrix, unrelated).
5. **Inspector with nothing selected = the container's Info.** Confirms the review's own
   recommendation — never "Nothing to Show"; the Inspector stays the native trailing column
   for now, and the `.inspector` pane kind stays hidden from the kind-switcher menu
   (`PaneSpec.Kind.selectableKinds`) until increment 7 makes it a real leaf.

## Rulings, third round (creative director, 2026-09-18) — increment 5c's browser

6. **The research project's embedded browser lives INSIDE the Source/Preview pane — no
   browser pane kind, no tab strip of its own.** `PaneSurface.webBrowser` as a Source
   rendition stands, decided, not merely proposed — see increment 5c above. Two things the
   design must keep apart: SCRATCH browsing (finding a source — a search engine, a
   catalogue, any page visited while looking) is navigation, never a node, nothing persisted
   beyond a session-only back/forward trail; a SAVED source is the only thing that becomes a
   node, and only via an explicit save — either the page captured as a native `.webarchive`
   (URL + capture time), or, preferred where the page supports it, the page's EXTRACTED
   output saved as the artifact with the page recorded as its provenance rather than the page
   itself. The agent's tools reach for catalogue/repository APIs first; the browser is the
   fallback for API-less sites and the surface a human watches the agent work on. Every open
   and every save goes through the one audited action layer — the agent is a user, here as
   everywhere else. Retitled/added `m2p.browser-is-a-source-rendition`,
   `m2p.scratch-browsing-persists-nothing`, `m2p.saving-a-source-makes-a-node` below.

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
- `m2p.entity-row-reader` — **[GAP]** (#4804): the plan's `entitySelection` input is a Bool, so it
  cannot tell the Entities/Claims table with nothing focused (no Reader content, honestly
  empty) from one entity or claim row focused (its source document is readable — the table sets
  `detailDocument` to it). The arm is unwired today, so nothing regresses; whoever wires it must
  carry a payload, not a Bool, and give the focused row a document-driven Reader cell. Found by
  the Reader-column audit that 4b-1 made necessary. **Now a PREREQUISITE of → #4838** (the KG
  readable-paragraph Reader rendition, `kg/kg-readable-representation.md` Migration step 6):
  → #4838 needs to know WHICH entity/claim is focused to draw its paragraph, the same payload
  #4804 already identified as missing — #4804 should land first, or as the same delivery.
- `library.pane` — confirms the Library leaf's identity is stable across selections
- `pane.kindSwitcher` — the per-pane-head kind selector (`m2p.pane-head-parity`)
- `inspector.surface.<kind>` — which inspector surface is mounted, for the agreement test

## Open questions (per-file: what was not grounded in the review)

Where a research project's embedded browser renders was asked here (2026-09-18, planning
increment 5c) and is now ANSWERED by the third round of Rulings above (item 6, 2026-09-18):
the Source/Preview pane, `PaneSurface.webBrowser`, no new pane kind.

Nothing else in this spec's Behaviors/Migration/Risks/Persistence sections goes beyond a claim
the review verified with a file:line citation. The five Open Questions the Rulings section
above closed were the review's own recommendations where the epic asked the creative director
to decide; nothing was invented outside that set.
