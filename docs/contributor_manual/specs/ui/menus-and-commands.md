---
title: Menus & Commands — Design Spec
status: DRAFT
owner: creative director
tags: [menus, commands, macos-hig, contextual-menus, keyboard-shortcuts]
related: [panes-workspaces]
---

# Menus & Commands — Design Spec

> Milestone: menus-and-commands

> Manual: TBD — the user manual needs a "Menus and keyboard shortcuts" reference: what lives under
> each menu, the shortcuts worth learning (Search vs Find in Page, the workspace switches), and the
> rule that a contextual menu offers the same verbs as the menu bar.
>
> **DRAFT for review 2026-09-15.** The creative director's brief: "The menus are all in the View
> menu and not well organized. We want them consistent with contextual menus, but things properly
> placed like in the menu bar. Review everything and work out a better way." This spec is a
> **proposal + self-review** — not yet ratified.

Legend (as the panes spec): **[OK]** matches today · **[BROKEN]** code contradicts the intent ·
**[GAP]** designed, not built · **[PROPOSED]** this spec's recommendation.

---

## Changelog 2026-09-16 (dfa937946) — the first structural cut shipped

A slice of this spec's proposed structure landed in the CD live-testing pass. **The spec Status stays
DRAFT** — these are behavior markers, not a ratification:

- **`Read` + `Knowledge` top-level menus** replace the old `CommandMenu("Data")`, so the menu bar reads
  `Fichero · File · Edit · View · Go · Read · Knowledge · Window · Help` — the workflow-mapped bar.
  (Now `PageAndProjectMenuCommands`, wired at `FicheroApp.swift` in the `after: .toolbar` region; Read
  became Page and Knowledge became Project, ruled 2026-10-10.)
- **⌘F = Search** is the native library search field (`.searchable` owns ⌘F — **no menu twin**, so no
  second owner of the chord).
- **⌘⌥F = Find in Page** moved to the **Edit** menu (`ShowFindBarButton` in the `.textEditing` group),
  beside the native ⌘F Search — two distinct finds where macOS users expect them. This also freed the
  ⌘⌥F chord that was previously double-minted (the "Find in Artifact" twin), which is renamed
  **Find in Page** on both sites.
- **Enter Full Screen → ⌃⌘F** (was ⌘⌥F, at `ContentView+RootLayout.swift`) — the macOS-standard chord,
  and it clears ⌘⌥F for Find in Page. **Superseded 2026-09-17** (see the Changelog entry below): ⌃⌘F
  turned out to BE the real system Enter Full Screen chord, not a look-alike, so this command now
  collided with AppKit's own menu item — moved again, to ⌃⌘R.
- **Import + New Folder → File ▸ Import** (moved out of Knowledge; `FocusedNewFolderButton` +
  `FocusedImportFilesButton` under a File `Menu("Import")`) — getting sources in/out is File's job.
- **View submenus:** Reader Lens / Workflows / Chat / KG-view-mode compose as `Menu` flyouts (the
  ratified nesting), not flat sections.
- **Legacy "Layouts" preset section removed** from `WorkspaceCommandsSection` (the
  `WindowLayoutPreset` pane-visibility presets that sat beside the workspaces) — a workspace IS the
  layout ([[panes-workspaces]] `workspaces.one-system`).
- **Shortcut-uniqueness is now ENFORCED** by `Tests/Unit/general/Views/Shell/MenuShortcutUniquenessTests.swift`
  — it enumerates every ⌘⌥ chord the app mints and fails if two commands claim one (the ⌘⌥1→loupe and
  double-minted ⌘⌥F defects). Complements the older `MenuShortcutBoundaryTests`. **Broadened
  2026-09-17** (see below): the claim above was overstated — the original scan only matched the
  literal `[.command, .option]` array order and missed `toolButton(key:)` mints, `KeyboardShortcut(`
  constructor calls, every OTHER modifier family, and had no system-reserved denylist. It is now one
  table-driven scan across `App/` and `Views/Shell/`, covering every modifier family and checking
  against a macOS system-reserved chord list — the claim is true now for the reason it names.

---

## Changelog 2026-09-17 — Fabel review fixes: real system-shortcut collisions, missing Redo

A Fabel review of the whole menu/shortcut surface found several LIVE collisions with macOS's own
key equivalents (not just app-internal double-minting), plus a missing Redo. Fixed:

- **⌘⌥T "Select Text"** (`PreviewHeadControls.swift`) collided with the system Show/Hide Toolbar
  chord (the app's own `.toolbar` group is present) — moved to **⌘⌥U**.
- **⌘⌥H "Highlight"** (`PreviewHeadControls.swift`) collided with system Hide Others — moved to
  **⌘⌥Y** (mnemonic: yellow, the default highlight color).
- **⌘⌥D "Line"** (`PreviewHeadControls.swift`) — chosen originally only to avoid the Loupe's ⌘⌥L,
  it was ITSELF a second, uncaught collision with the system's Turn Dock Hiding On/Off — moved to
  **⌘⌥G**.
- **⌃⌘F "Enter Full-Screen Reading"** (`ContentView+RootLayout.swift`) collided with the real system
  Enter Full Screen chord (not a look-alike) — moved to **⌃⌘R**. It remains a hidden, menu-less
  `.opacity(0)` button: promoting it to a real Read/View menu item needs a `.focusedSceneValue`
  publish from `ContentView.swift`, left as a follow-up.
- **⌃⌘S "Show Side Preview"** (`ViewMenuLayoutSections.swift`) sat on the HIG Show/Hide Sidebar
  chord while no Show/Hide Sidebar command existed (`toggleSidebar()` in
  `ContentView+ActionsUI.swift` has zero callers) — moved to **⌃⌘J**, freeing ⌃⌘S. Wiring an actual
  Show/Hide Sidebar command onto ⌃⌘S needs the same `.focusedSceneValue` publish as above and is
  also left as a follow-up; `MenuShortcutUniquenessTests` denylists ⌃⌘S in the meantime so nothing
  squats on it by accident.
- **Toolbar "Inspector (⌘⌥I)" help text** (`ContentView+Toolbar.swift`) named the wrong chord — the
  real one is **⌃⌘I** (`ViewMenuPaneSections.swift`); ⌘⌥I is "Copy Files". Text corrected.
- **Two "Zoom to Fit" chords for one verb** — Canvas (⌘=) vs Read ▸ Zoom (⌘9) — unified onto **⌘=**
  everywhere: the two commands are gated by mutually-exclusive focused values, so sharing the
  physical chord is safe and gives the verb one muscle-memory chord instead of two. **Superseded
  2026-09-18** (see the Changelog entry below): ⌘= turned out to be the wrong shared chord — AppKit's
  key-equivalent matching let it also intercept ⌘+ — so both sites moved to **⌘9** instead.
- **File ▸ Import ▸ Import double nesting** (`FileMenuCommands.swift`) — flattened; New Folder and
  the Import submenu (Link/Copy/Move) now render as siblings, not double-wrapped.
- **Redo did not exist.** `CommandGroup(replacing: .undoRedo)` supplied `UndoLastActionButton()`
  alone, so a focused text editor could undo a sentence but never get it back. Added
  `RedoLastActionButton` (`FocusedCommandButtons+UndoNavigation.swift`) on **⌘⇧Z**, routed the same
  way as Undo (`RedoRoute`/`RedoRoutingPolicy` in `UndoRouting.swift`): a focused text editor's own
  undo manager, else the audited-action log's newest still-undoable INVERSE row (undoing an undo
  re-applies the original — no new backend endpoint needed).
- Stale **"six workspaces" / "⌘⌥1–6"** text corrected to **five / ⌘⌥1–5** across this spec,
  `ViewMenuCommands.swift`, `ViewMenuPaneSections.swift`, `ContentView+LayoutChooser.swift` (comments
  only), and `MenuShortcutUniquenessTests.swift`. Stale **"Library layout (⌘1–4)"** corrected to the
  real ⌘1–6. A stale "Search" button reference in `FocusedCommandButtons.swift`'s module doc-comment
  (no such button exists) removed.

**Known, deliberately NOT fixed in this pass** (different file ownership / out of this lane's scope):
the ⌘'/⌘⇧' Back/Forward chords were minted independently in THREE places — the Go menu
(`FocusedCommandButtons+UndoNavigation.swift`, the intended single owner), the main toolbar
(`ContentView+Toolbar.swift`), and `OntologyBrowser+Toolbar.swift` — with no single owner. **Fixed
2026-09-18** for the first two (see the Changelog entry below) — `ContentView+Toolbar.swift` no
longer mints the chord, only `FocusedCommandButtons+UndoNavigation.swift` does. The third mint
resolved a different way, not by a chord fix: `OntologyBrowser+Toolbar.swift` was DELETED whole
(#4705 increment 3, 2026-09-18 — the KG sidebar mode retired), taking its independent mint down
with it. The Go menu is the sole remaining owner.

Still **[PROPOSED]** / unbuilt: the AddItemMenu/Data dedupe, the context-menu component reuse, and
Sort/Workspaces re-homing. A **top-level** Workspaces menu (and top-level Find/Workflows menus) were
**declined** — Workspaces stays a View submenu, Find lives in Edit.

---

## Changelog 2026-09-18 — adversarial review of the 2026-09-17 pass: a live AppKit collision, a double-mint, a redo bug, and a false-positive-prone guardrail

A follow-up review of the 2026-09-17 fixes (above) found the unification itself introduced one new
live collision, left one double-mint only partially fixed, and the guardrail's own denylist was
producing false positives. Also found and fixed: Redo re-offering itself after redoing. Fixed:

- **Zoom to Fit moved from ⌘= to ⌘9** (`CanvasMenuCommands.swift`, `ImagePreviewMenuCommands.swift`).
  The 2026-09-17 unification onto ⌘= was itself a live bug: AppKit's key-equivalent matching for an
  item whose modifier mask omits `.shift` checks `charactersIgnoringModifiers`, which strips Shift
  back to the UNSHIFTED base character even when Shift IS held — so the bare-⌘= "Zoom to Fit" item
  also intercepted ⌘⇧= (i.e. ⌘+) and won the match ahead of "Zoom In" (earlier in the menu). ⌘9 shares
  no physical key with the ⌘+/⌘- zoom chords, so it cannot repeat that. The two commands' deliberate
  cross-file sharing (`hasFocusedCanvas` / `hasActiveImagePreview` mutually exclusive) is unchanged,
  just on a safe chord.
- **Back/Forward (⌘'/⌘⇧') has one chord owner now.** The 2026-09-17 entry above flagged three
  independent mints with no single owner. The toolbar's `.keyboardShortcut` calls
  (`ContentView+Toolbar.swift`) are removed — the toolbar Back/Forward buttons are click-only mirrors
  of the Go menu's `NavigateBackButton`/`NavigateForwardButton`
  (`FocusedCommandButtons+UndoNavigation.swift`), the sole remaining owner. The third mint
  (`OntologyBrowser+Toolbar.swift`) is resolved separately, below.
- **Redo (⌘⇧Z) no longer re-offers itself after redoing.** `RedoLastActionButton.performRedo` reversed
  a redo target the same way as any other row (`AuditStore.undo(_:)`), which writes a NEW audit row
  that is itself `inverseOf`-set and not yet undone — structurally identical in shape to a genuine
  redo target, so a naive filter offered it right back: a SECOND ⌘⇧Z undid the redo it had just
  performed instead of being a no-op. Fixed with `AuditStore.nextRedoable(in:)`: a redo target must be
  an inverse of a genuine FORWARD action (`inverseOf == nil`), never an inverse of another inverse.
  Pure-tested in `Tests/Unit/general/Models/AuditStoreRedoTests.swift` (press undo → redo → redo again
  leaves state "redone", not "undone").
- **The system-reserved chord list is now exactly the eight chords AppKit owns UNCONDITIONALLY**
  (`MenuShortcutUniquenessTests.systemReservedChords`): **⌘⌥H** (Hide Others), **⌘⌥T** (Show/Hide
  Toolbar), **⌘⌥D** (Turn Dock Hiding On/Off), **⌃⌘F** (Enter Full Screen), **⌃⌘S** (reserved,
  unwired — no Show/Hide Sidebar command exists yet), **⌘H** (Hide Fichero), **⌘Q** (Quit Fichero),
  **⌘,** (Preferences…). The Format-menu chords (⌘T/⌘I/⌘B/⌘U/⌘+/⌘-) that used to sit in this same list
  are REMOVED — they are NOT system-reserved. They are SwiftUI's built-in `TextFormattingCommands()`
  (wrapped by `FormatMenuCommands`), which only claims a live key equivalent while a focused text view
  accepts it; denylisting them unconditionally produced false positives against always-enabled
  commands reusing the same key with no text editor focused — File's ⌘T (then "New Window", now "New Tab", #5286), Image Preview's
  ⌘+/⌘- "Zoom In"/"Zoom Out", and the sidebar's ⌘I "Link Files…" all tripped the guardrail though none
  of them can ever fire at the same moment as the Format item they were flagged against.
- **The shortcut-uniqueness guardrail is now `#if`-aware.** `MenuShortcutUniquenessTests` tracks
  `#if`/`#elseif`/`#else`/`#endif` nesting per file and tags every mint with its conditional-
  compilation branch path; two mints of the same chord collide only if their branch paths are NOT
  proven mutually exclusive (same branch, or one at file scope alongside any branch — different,
  unrelated `#if` conditions are never assumed exclusive either). This is what let
  `ShowFindBarButton`'s ⌘⌥F — declared once inside `#if canImport(AppKit)` and once in the matching
  `#else` (`ViewMenuPaneSections.swift`) — drop out of the manual `allowedSharedChords` allowlist
  entirely: the scanner now proves the two bodies can never both compile, instead of needing a
  human-maintained exception. (This also fixed a real gap: the prior grouping counted DISTINCT FILES
  per chord, so two mints of the same chord in one file were invisible; every mint site counts now.)
- **The Knowledge menu's "Knowledge Graph View" item is gone; "SPARQL Console…" replaces it**
  (#4705 increment 3: the KG sidebar mode + its `OntologyBrowser` UI retired — creative director,
  "the ⌃⌘1…9 Sidebar-mode entries are removed"). `KnowledgeGraphViewModeSection`
  (`ViewMenuLayoutSections.swift`) — the List/Graph/Chart/Timeline/Map switcher for `OntologyBrowser`'s
  own mode — retired with its subject; there is no entities-table equivalent to offer in its place.
  The W3C SPARQL console it also hosted as a sheet is NOT retired (creative director, 2026-06-25
  ruling #2593/#2614: "SPARQL is wanted and must be made VISIBLE; never delete it") — recovered into
  its own file (`Views/SPARQLConsole/SPARQLConsoleView.swift`) and its own `Window("SPARQL Console",
  id: "sparql-console")` scene, opened via the new Knowledge-menu button, no keyboard shortcut. The
  "predict entities" flow the KG sidebar mode also carried (`HeuristicReviewSheet`, backed by
  `kg_predictions`/heuristic) was NOT recovered — it had no caller outside the deleted
  `OntologyBrowser+Sheets.swift`/`+Toolbar.swift`/`+List.swift` and is now unreachable anywhere in the
  app, confirming #4759's finding; routed to #4791/#4759 for a product decision, not silently dropped
  here.

---

## Changelog 2026-09-19 — legacy milestone fold (#131 "UX - Mac - Menus, Commands & Shortcuts")

Grounding pass against HEAD for this legacy milestone's 8 open issues (Pass 1 — findings only,
issue moves not executed this pass). Two of the eight are this spec's own subject; three belong
to sibling specs (export-pipeline, audited-action-layer) and are cross-referenced there, not
restated here; three are a cluster of undo-scope GAPs living in `audited-action-layer.md`.

- **#3302 and #4185, verify-close against `menus.undo-reaches-every-mutating-action` below.**
  Both describe the same gap this milestone opened them for — ⌘Z reaching only the entity-merge
  button, no Redo, silent undo failures — and all three are now built and tested. See the
  behavior below for the evidence; not restated here.
- **#3307 (iPad menu parity)** is a live GAP, not touched this pass — see
  `menus.ipad-full-parity` below.

---

## RULED 2026-10-10 — the Project menu, stage by stage

The maintainer ruled the menu bar's shape and its one rule for verbs:

- **The bar:** `Fichero · File · Edit · View · Go · Page · Project · Window · Help`. **Project** replaces
  **Knowledge**, which retires. **Read** becomes **Page**, and the Segment menu folds into it (built
  2026-10-12, #5652 slice 2, `menus.page.replaces-read-and-segment`).
- **Project** is one menu: **Set Up…** and **Start** (⇧⌘↩) at the top, then one titled section per
  recipe stage, in the order a recipe runs them: **Read · Organise · Structure · Connect · Train**. A
  stage lists only verbs the app has; a stage with none yet shows nothing.
- **Every context-menu verb is also in the menu bar**, through ONE shared `Focused*Button` (or the one
  `*MenuItem` it renders), so the two never disagree (`menus.context-matches-bar`).
- **File makes, opens and closes projects;** it says Project, never Library (renamed 2026-10-03), and
  `…`, never `...`. Setting up the key window's project is Project › Set Up….

Behaviours (slice 1):

- `menus.project.bar` — **[OK]** (#5652) **Built 2026-10-10 (app), not yet seen:** a top-level
  **Project** menu replaces Knowledge (`CommandMenu("Project")` in `PageAndProjectMenuCommands.swift`,
  composed there because the app's `.commands` builder is at its 10-entry limit); pinned by
  `MenuTerminologyBoundaryTests.testProjectMenuDeclaresTheStageSectionsInRecipeOrder`. Read → Page is
  built 2026-10-12 (`menus.page.replaces-read-and-segment`), so the bar reads as ruled.
- `menus.project.setup-and-start-first` — **[OK]** **Built 2026-10-10 (app), not yet seen:** Project's
  first items are **Set Up…** (`FocusedSetUpButton`, the window's `setUpProjectAction`, the same setup
  as Inspector › Recipe › Set Up…) and **Start** ⇧⌘↩ (`FocusedStartRecipeButton`, the same
  `RecipeSetupStore.start` call setup's Start makes; a plan not read yet is read on the press; a plan
  that cannot start opens Set Up… so its steps say why; a kept Start lands on the run in Activity, as
  setup's does). **Allow Cloud AI Services for This Project** follows them (`FocusedCloudSwitchButton`, a toggle
  for the key window's project: `RecipeSetupStore.allowCloud(allowed:)`, the Inspector's switch, #6022). Each is disabled with its reason under it when there is no project, or when the plan
  refuses (the refusal is the reason); pinned by
  `fichero/Tests/Unit/general/App/MenuTerminologyBoundaryTests.swift` (`testProjectMenuDeclaresTheStageSectionsInRecipeOrder`),
  `testStartSaysWhyItCannotAct`, and `MenuShortcutUniquenessTests.projectMenuChordsAreUnique`.
- `menus.project.stage-sections` — **[PARTIAL]** (#5652) **Built 2026-10-10 (app), not yet seen:** the
  stages are `ProjectMenuStage` in recipe order, each a titled `Section`: **Read** › Reading ▸ › Run the
  Recipe on This Folder… (`RunRecipeOnFolderMenuItem`, also in both folder context menus; #5540,
  `source.recipe.folder-scoped-start` in `source/models-chains-and-projects.md`), **Organise** › Find the
  Documents (⇧⌘D), **Connect** › SPARQL Console… (moved from Knowledge), **Train** › Train a Model… and
  Make Available in Every Project (`menus.project.train`); **Workflows ▸** and **Chat ▸** (moved from
  Knowledge) follow the stages. *Not built:* **Structure** (no verb yet).
- `menus.project.find-the-documents-one-component` — **[OK]** **Built 2026-10-10 (app), not yet seen:**
  Find the Documents is ONE item, `FindDocumentsMenuItem` (`FocusedCommandButtons+Recipe.swift`),
  rendered by Project › Organise (`FocusedFindDocumentsButton`, on the key window's library selection,
  else the folder the window shows), the library's context menu and the sidebar's (on the clicked
  folder, or the selection it is part of); what it looks through is one pure policy,
  `FindDocumentsScope`. Disabled with its reason when there is no project or nothing fits. The chord
  is **⇧⌘D**, not ⌥⌘K, which the Preview's Check markup tool already has; pinned by
  `MenuTerminologyBoundaryTests.testFindTheDocumentsIsOneComponent`, `testFindDocumentsScope`, and
  `MenuShortcutUniquenessTests.projectMenuChordsAreUnique`.
- `menus.file.says-project` — **[OK]** **Built 2026-10-10 (app), not yet seen:** File reads Set Up New
  Project…, Open…, Open Recent ▸ (No Recent Projects), Close Project, … Save Project As…, Export ▸
  (BibTeX (.bib)…, Markdown Static Site…), Grant Folder Access…; File › Set Up Project… is gone (it is
  Project › Set Up…); pinned by
  `MenuTerminologyBoundaryTests.testFileMenuLabelsSayProjectAndUseTheEllipsis`.
- `menus.project.activity-stop-read-again` — **[OK]** (#5652 slice 3) **Built 2026-10-12 (app), not yet
  seen:** Project › Activity › **Stop** and **Read Again** act on the Activity window's one selected run
  (`FocusedActivityRunButtons`, on the `activityRun` focused value the window publishes). Each is ONE
  item, `ActivityStopMenuItem` / `ActivityReadAgainMenuItem` (`FocusedCommandButtons+Activity.swift`),
  rendered by the menu bar, the Activity table's context menu and the row's own icon buttons, the
  Activity details' actions, its stage cards and summary, and the project window's run strip. Every one
  acts on an `ActivityRunMenuTarget` made by `make(…)` (a row) or `stage(…)` (one stage's failed pages),
  whose closures are the only place the app calls `ActivityStore.cancelJob` and `readPagesAgain` for
  them: one code path. Read Again reads as the run's own offer ("Read the 3 pages
  that failed"). Disabled with its reason under it when no run is selected, when the run is not running
  or waiting (Stop), or when it has ended with nothing to read again (Read Again). No chords: ⌘. is the
  system's cancel. Pinned by `ActivityRunMenuTests` and
  `MenuTerminologyBoundaryTests.testActivityStopAndReadAgainAreInTheMenuBar`.
- `menus.project.train` — **[OK]** (#5652 slice 1) **Built 2026-10-12 (app), not yet seen:** Project ›
  Train holds **Train a Model…** and **Make Available in Every Project** (`FocusedTrainButtons`,
  `FocusedCommandButtons+Train.swift`). Train a Model… is ONE item, `TrainModelMenuItem`: it opens the
  project's Set Up on its **Train** page (`SetupStep.opening(requestedStage:)` → `.train`, the Start
  plan's train offers in `RecipeTrainOffersFields`, read there when no page before has), no new flow.
  Make Available in Every Project is ONE item, `MakeModelGlobalMenuItem`, on the model selected in the
  sidebar's **Models** node (`ProjectMenuTarget.trainedModel`); the same two items are the model row's
  context menu (`SidebarModelsNode`, the type renamed from `SidebarTrainingNode` to match the node's
  ruled name), and the Inspector's button is the same Make Available item. All act through
  `TrainedModelMenuTarget.make`, over `TrainedModelsStore.makeAvailableEverywhere` (one code path; the
  outcome is kept by model id for the Inspector to say). Disabled with its reason under it: no project
  (Train a Model…), no model selected, already available everywhere, or under way (Make Available). No
  chords. Pinned by `ProjectTrainMenuTests`,
  `TrainedModelNodeActionsTests.makeAvailableThroughTheSharedTarget`,
  `MenuTerminologyBoundaryTests.testTrainAndTheModelVerbAreOneItemEverywhere` and
  `testProjectMenuDeclaresTheStageSectionsInRecipeOrder`.
- `menus.page.replaces-read-and-segment` — **[OK]** (#5652 slice 2) **Built 2026-10-12 (app), not yet
  seen:** the top-level **Read** menu is **Page** and the **Segment** menu folded into it: Page holds
  Reader Lens ▸, Next / Previous Doubtful Word (⌃⌘G / ⇧⌃⌘G), Zoom ▸, Rotate Left / Right (⌘L / ⌘R), and
  a **Segments** section with the Segment menu's items (Edit Segments, Delete, Join ⌘J, the attributes),
  each still disabled with its reason under it. Every item is the same shared section it was and kept
  its chord. The composing type is `PageAndProjectMenuCommands` (was `ReadKnowledgeMenuCommands`).
  Pinned by `PageMenuTests`, `MenuTerminologyBoundaryTests.testPageMenuReplacesReadAndSegment` and
  `MenuShortcutUniquenessTests.pageMenuChordsAreUnique`.
- `menus.edit.segments-submenu` — **[GAP]** (#6413; ruled 2026-11-08 by the owner) the **Segments** section leaves Page for an **Edit › Segments ▸** submenu: the same shared section (`SegmentMenuContent`) with the same chords, rendered by every context menu too (`source/segment-editor-crud.md`, `source.editor.edit-segments-submenu-and-doors`, Step 1.2); Page keeps Reader Lens ▸, the doubtful-word steps, Zoom ▸ and Rotate; Delete keeps ONE keyed home, Edit › Delete ⌘⌫, and the submenu's Delete has no chord of its own; Group/Make New From Selection (⌥⌘G proposed), Ungroup (⌥⇧⌘G proposed) and Split (⌥⌘S proposed) join the submenu with their chords checked here; ⌘G stays Find Next. *Test:* the existing `PageMenuTests.swift` and `MenuShortcutUniquenessTests.swift` (the page menu case moves, the uniqueness case gains the submenu's chords), `SegmentDoorsAgreeTests.swift` (not yet written).
- `menus.project.run-recipe-on-this-item` — **[GAP]** (#6411, #4552; owner 2026-11-08: a recipe cannot be run on ONE selected file or PDF; today `RunRecipeOnFolderMenuItem` is rendered only for a folder row (`LibraryView+ContextMenu` passes `isFolder: document.docType == .folder`; the sidebar's folder row), `RecipeFolderScope.forClick` answers nothing for a page, and running a workflow on one PDF ran on every sidebar item, #4552) the same one item, relabelled by what it acts on ("Run the Recipe on This Folder…", "… on This PDF…", "… on This Document…", "… on These 3 Items…"), is rendered by the file, PDF and group rows' context menus in the Library pane, the Preview's folder views and the sidebar, and runs on EXACTLY the clicked selection, never the sidebar's selection or the window's folder (the #4552 scope rule): the clicked row alone when it is not part of the selection, the whole selection when it is (Finder semantics, as `RecipeFolderScope.forClick` already does for one folder; it gains the other kinds and a set of ids). The engine's folder-scoped start (`source.recipe.folder-scoped-start`, `folder_id` on the Start plan and `start`) takes the scope as the ids it already takes, worked out to pages the same way: a folder or group to its pages, a PDF to its pages, a page or file to itself; a scope with no pages refuses Start in words; nothing outside the scope is touched, and a model pass already landed on a page in it is reused (`activity.read.page-read-once`). No new route: the Start plan's scope field widens from one folder to the ids of the selection; the item, the plan read and the start are the existing component. Acceptance: right-clicking one PDF in a folder of twenty and choosing Run the Recipe on This PDF… starts a run whose Activity row names that PDF and reads its pages and no other; with three rows selected and one of them right-clicked the item reads "… on These 3 Items…" and runs on the three; a right-click on a row outside the selection runs on that row alone. *Test:* `MenuTerminologyBoundaryTests.testRecipeFolderScope` (the existing test, extended to the other kinds and the selection set), `test_start_scope_is_the_selection_6411.py` (not yet written), `RunRecipeScopeLabelTests.swift` (not yet written).
- `menus.project.run-recipe-shortcut` — **[GAP]** (#6411) the menu-bar item in Project › Read › Reading ▸ (`FocusedRunRecipeOnFolderButton`) acts on the window's current selection by the same scope rule (`RecipeFolderScope.forSelection`: the selection when there is one, else the folder the window shows), carries the label of what it acts on and ONE keyboard shortcut (⌥⌘R proposed; `MenuShortcutUniquenessTests.projectMenuChordsAreUnique` and the system-shortcut audit decide, as `menus.shortcut-uniqueness` rules), and when it cannot act is disabled with its reason in words ("Select an item or a folder to run the recipe on"; "Open a project to start its recipe"; the plan's refusal), never silent. Acceptance: with a PDF selected ⌥⌘R starts the run on it and the menu item read "Run the Recipe on This PDF…  ⌥⌘R"; with nothing selected in a window showing a folder it runs on the folder; with no project it is disabled with the reason. *Test:* `PageMenuTests.readingSubmenu` (the existing test, extended), the existing `MenuShortcutUniquenessTests.swift`, `RunRecipeScopeLabelTests.swift` (not yet written).
- `menus.project.read-reading-submenu` — **[OK]** (#5652 slice 2) **Built 2026-10-12 (app), not yet
  seen:** Project › Read holds a **Reading ▸** submenu of the reading verbs on the selection. Today it
  holds the one such verb the app has, **Run the Recipe on This Folder…** (`FocusedRunRecipeOnFolderButton`
  over `RunRecipeOnFolderMenuItem`, the item both folder context menus render), disabled with its reason
  (no project; not one folder). Read with Another Model… and Find Where the Readers Disagree stay on the
  disagreement lens (no selection of their own); which further verbs join Reading ▸ is an open question
  on #5652. Pinned by `PageMenuTests.readingSubmenu` and
  `MenuTerminologyBoundaryTests.testProjectMenuDeclaresTheStageSectionsInRecipeOrder`.
- `menus.edit.item-verbs-one-component` — **[OK]** (#5652 slice 4, group 1) **Built 2026-10-12 (app), not yet
  seen:** Rename, Delete, Exclude from / Include in Processing, Search and Everywhere, Bookmark…, Add to Workspace…,
  Export a Copy… (was Export…), Group and Ungroup (was Group as Stack) are ONE item each
  (`FocusedCommandButtons+ItemVerbs.swift`; Group and Ungroup in `RotateImageCommands.swift`). The sidebar's row
  menu and the Items list's context menu render them on the clicked row (the selection when the click is part of
  it), and **Edit** renders them on the focused pane's selection (`ItemVerbsTarget`, published by the Items list as
  the `itemVerbs` focused value; the sidebar's selection through its own Rename and Delete), with **File › Export a
  Copy…** beside Export ▸. Each menu-bar item is disabled with its reason under it. Exclusion is one operation
  (`ItemVerbs.setExcluded`) and grouping one (`ItemGrouping`, the node named "Group of N"), whichever surface
  presses. Chords kept: Rename is Return while the sidebar has focus (in Items, Return opens the row), Delete is
  ⌘⌫. *Not yet:* from the sidebar's selection, Exclude, Bookmark…, Add to Workspace… and Export a Copy… in the
  menu bar say to select the document in Items (the sidebar's pickers are per row). Pinned by `ItemVerbsMenuTests`
  and `MenuVerbsOneCodePathGuardTests.itemVerbWordsLiveInOnePlace`.
- `menus.file.open-verbs-one-component` — **[OK]** (#5652 slice 4, group 2) **Built 2026-10-12 (app), not yet
  seen:** Open, Open in New Tab, Open in New Window, Duplicate, Make Alias, Show Original (or Reveal) in Finder,
  Quick Look and New Folder are ONE item each (`FocusedCommandButtons+OpenVerbs.swift`; `OpenInMenuItems` renders the
  open three for every surface that has them). The sidebar's and the Items list's context menus render them on the
  clicked row; **File** renders them on the focused pane's selection (`ItemVerbsTarget`), each disabled with its
  reason under it, Show Original as the context menus' own `RevealOriginalMenuItem` or why it is not there. Chords
  kept: Open in New Tab ⌥⌘O, Open in New Window ⇧⌥⌘O, New Folder ⇧⌘N (now also in the Items list's folder); none
  added. Import was already one handler (File › Import ▸ through the focused pane). *Not yet:* from the sidebar's
  selection, File's Open, Duplicate, Make Alias and Quick Look say to select it in Items (the row's own). Pinned by
  `ItemOpenVerbsMenuTests` and `MenuVerbsOneCodePathGuardTests.itemVerbWordsLiveInOnePlace`.
- `menus.page.line-verbs-one-component` — **[OK]** (#5652 slice 4, group 3) **Built 2026-10-12 (app), not yet
  seen:** Correct This Line…, Open (a segment that holds others) and Create Named Order are ONE item each
  (`FocusedCommandButtons+LineVerbs.swift`): the Reader's line rows and the Order list's rows (Correct This Line…),
  the Segments pictures (Open) and the Order list's no-order row (Create Named Order) render them, and **Page ›
  Segments** renders them on the focused list's selection (`LineVerbsTarget`, the `lineVerbs` focused value the
  Order list, the selected Reader line and the selected picture publish), each disabled with its reason under it.
  The undo step's name is the item's title. No chords. Pinned by `LineVerbsMenuTests` and
  `MenuVerbsOneCodePathGuardTests.itemVerbWordsLiveInOnePlace`.
- `menus.edit.proposals-and-direction` — **[OK]** (#5652 slice 4, group 4) **Built 2026-10-12 (app), not yet
  seen:** **Edit › Proposed Document ▸** renders the Items list's own menu over proposed documents
  (`ProposedDocumentsMenu`: Accept, Reject and, for one, Split Here, Move Page and Join with Next) on the proposals
  the focused selection names, answered through the list's one path (`answerProposals`); **Edit › Direction ▸**
  renders the Items list's and the Inspector's own `SourceDirectionMenu` on one selected folder, document or page,
  with the window's steps for ⌘Z (`FocusedCommandButtons+ProposalVerbs.swift`). Each is disabled with its reason
  under it otherwise. Pinned by `ProposalAndDirectionMenuTests` and
  `MenuVerbsOneCodePathGuardTests.itemVerbWordsLiveInOnePlace`.
- `menus.file.project-verbs-one-component` — **[OK]** (#5652 slice 4, group 5) **Built 2026-10-12 (app), not yet
  seen:** Rename Project…, Edit Document Types…, Share Project…, Show in Finder, Delete Project… and Close Project
  are ONE item each (`FocusedCommandButtons+ProjectVerbs.swift`): a project's row menu and the always-there
  project's empty-area menu render them on their project, and **File** (Rename, Share, Show in Finder, Delete,
  Close Project ⌃⌘W) and **Project › Edit Document Types…** render them on the key window's project
  (`ProjectVerbsTarget`, published by that project's row, or by the sidebar for the always-there project), each
  disabled with its reason under it (the always-there project's kind, a viewer's access, no project). Activity's
  Delete is Edit › Delete's item (⌘⌫ on the selected runs). The sidebar's automation rows' Pause, Resume, Run Now and
  Cancel were found unwired (no caller passes their actions): they are disabled rather than presses that do
  nothing, and have no menu-bar item until they are wired (#5652). Pinned by `ProjectVerbsMenuTests` and
  `MenuVerbsOneCodePathGuardTests.itemVerbWordsLiveInOnePlace`.
- `menus.project.run-and-chat-one-component` — **[OK]** (#5652 slice 4, group 6) **Built 2026-10-12 (app), not yet
  seen:** Run Workflow ▸ and Add to Chat are ONE item each (`FocusedCommandButtons+RunAndChatVerbs.swift`): Run
  Workflow ▸'s shell (its label, the scope it says before the run — "Runs on N documents", "Runs on this item only —
  it is outside your selection" — and "Nothing to run on") holds each surface's own workflow list (the sidebar's
  sections, the Items list's folders), and **Project › Workflows ▸ Run Workflow ▸** renders it on the focused Items
  list's selection, run through the list's one batch run; Add to Chat is the sidebar's and the Items list's item and
  **Project › Chat ▸ Add to Chat** on the focused selection. Each is disabled with its reason otherwise. Run Workflow
  on Selection… (⇧⌘R, the picker) stays beside it. Pinned by `RunAndChatMenuTests` and
  `MenuVerbsOneCodePathGuardTests.itemVerbWordsLiveInOnePlace`.
- `menus.edit.exclusion-everywhere-one-way` — **[OK]** (#5652 slice 4, group 7) **Built 2026-10-12 (app), not yet
  seen:** the dataset rows' menu (its fixed Exclude from Processing, Exclude from Search, Include Everywhere: a row
  carries no exclusion state) and the Inspector header's one-document toggle take their words from `ItemVerbs`
  and exclude through its one operation (`ItemVerbs.setExcluded`), as the browse menus and Edit do; the words are
  spelled nowhere else. Pinned by `ItemVerbsMenuTests` and
  `MenuVerbsOneCodePathGuardTests.itemVerbWordsLiveInOnePlace`.
- `menus.project.automation-verbs` — **[OK]** (#5712, #5652 slice 4) **Built 2026-10-12 (app), not yet seen:** a
  schedule's Pause, Resume and Run Now, a trigger's Pause and Resume, and a batch's Pause, Resume and Cancel Batch
  are the engine's own actions (`/api/schedules/{id}/pause|resume|trigger`, `/api/triggers/{id}/pause|resume`,
  `/api/batches/{id}/pause|resume|cancel`, through `AutomationAPIService` and `BatchService`), offered by the row's
  state (`AutomationVerbs.offered`), ONE item each (`FocusedCommandButtons+AutomationVerbs.swift`): the row's menu
  renders them, and **Project › Workflows ▸** renders them on the sidebar's selected automation row, each disabled
  with its reason. After a verb the sidebar reads its schedules, triggers and runs again; a refusal is said on the
  sidebar's banner. They had been offered with no action behind them (found in group 5). The sidebar's
  `AutomationAPIService` had answered every call with nothing (no schedule or trigger was ever listed); it now
  goes through the one typed `AutomationService` on the project's generated client, and renames through the update
  route. Pinned by `AutomationVerbsMenuTests`.
- `menus.context-matches-bar.slice-4-done` — **[OK]** (#5652) every context-menu verb the 2026-10-12 inventory
  listed is in the menu bar through its one shared component (groups 1-7 and #5712 above).

---

## Intent (the design)

A command exists **once** and appears wherever it is useful — the menu bar (discovery, keyboard
shortcuts, the full set), and the contextual right-click menu (the focused subset for what's under
the cursor). The two must never disagree: same label, same icon, same shortcut, same enablement,
because they render from the **same definition**. Commands live in their **natural top-level menu**
(macOS HIG): File acts on the document/library, Edit on the selection, View on appearance and
layout, and feature menus (Data) on the domain. The View menu is not a junk drawer.

This is the same "one system, well done" principle the workspace spec ratified
([[panes-workspaces]] §`workspaces.one-system`): **one source, many surfaces.**

---

## Current architecture (grounded, 2026-09-15) — a junk-drawer View menu + duplicated verbs

Menu bar top level (`FicheroApp.swift` `.commands`): **App · File · Edit · View · Go · Data ·
Format** (+ per-scene `.commandsRemoved()` on auxiliary windows).

**Finding M1 — the View menu is a catch-all.** `ViewMenuCommands` (App/Menus/ViewMenuCommands.swift)
stacks ~12 sections behind one menu:

| Section | Belongs in View? | Note |
|---|---|---|
| Sidebar mode | yes | appearance |
| Library layout (⌘1–6) | yes | list/grid/table/graph |
| **Sort** | **weak** | sorting is data ordering, not appearance; buried here |
| Preview mode | yes | |
| Representation | yes | which rendition is shown |
| Knowledge-graph view mode | yes | |
| Inspector (⌃⌘I) | yes | |
| **Reader lens ("Showing")** | partial | what the reader renders — view-ish, but deep |
| Canvas view | yes | |
| Pane visibility | yes | |
| **Workspaces (⌘⌥1–5)** | **no** | a top-level concern; competes with the pane toggles |
| Workflow bar / labels / Find bar | yes | chrome toggles |

Twelve sections, five dividers, in one menu. A user hunting for Sort or Workspaces scrolls past
appearance toggles that have nothing to do with either.

**Finding M2 — the menu bar and contextual menus are HAND-BUILT TWINS that drift.** The same verbs
are re-authored per surface with no shared source:

- **Creation verbs appear twice.** The menu-bar **"Data"** menu (`FicheroApp.swift`) lists New
  Folder, Import Files, New Chat / Workflow / Comparison / Chain / Schedule / Trigger, Run Workflow
  on Selection — and the toolbar **"+" `AddItemMenu`** lists the *same* set again, independently.
  Two definitions of "New Workflow" → their labels, icons, feature-gating and shortcuts can (and do)
  diverge.
- **Reader export appears twice** — File ▸ Export and the reader head's context menu
  (`ReaderExportMenuItems` is shared here, which is the RIGHT pattern; most others are not).
- **~20 contextual menus** (`grep .contextMenu`: Sidebar rows, Library table/list/icon/graph rows,
  Inspector KG, Workflow canvas, PDF/image previews, the pane head) are each built inline. Nothing
  guarantees a row's right-click "Delete" is the same verb (label, shortcut, enablement) as Edit ▸
  Delete or the toolbar's.

**Finding M3 — no typed command catalog.** Commands are expressed as ad-hoc `Button`s inside each
`CommandMenu`/`contextMenu`, wired to actions via `@FocusedValue` in some places (good: the reader
lens, select-all, delete) and via direct closures in others (drift-prone). There is no single list
of "the app's commands" that both surfaces consume, so consistency is manual and therefore lossy.

---

## Menu bar STRUCTURE — proposed 2026-09-15 (workflow-grounded, Apple HIG) — FOR CD REVIEW

> CD: "The top-level menus don't seem enough — how it is now isn't clear. A user might be browsing,
> reading, transcribing, updating data, exporting… Review the app and think through what should be
> there." Reviewed against Apple's Menus & Actions HIG and the guide's workflow (Parts I–IX).

**The problem isn't only that View is a junk drawer — it's that the menu bar doesn't mirror what the
user DOES.** Today: `Fichero · File · Edit · View · Go · Data · Format`. "Data" is really "create
things" (New Chat/Workflow/…), the reading/annotating/knowledge verbs are scattered in View, and
there's no menu that reads like a stage of the work. Apple HIG: *organize items to reflect how people
use the app; important items first; group logically; submenus sparingly (one level, ≤~5 items) and
only when a term repeats.*

**Proposed menu bar — top level maps to the WORKFLOW (READ → THINK → WRITE, EPIC #2108):**

`Fichero · File · Edit · View · Go · Read · Knowledge · Window · Help`

> **[OK] SHIPPED (dfa937946, 2026-09-16):** this top-level bar is the live structure — `Read` and
> `Knowledge` (`PageAndProjectMenuCommands`) replace the former `CommandMenu("Data")`. The remaining
> per-menu item placements below are still the proposal; only the top-level bar and the
> Import/Find/Full-Screen moves (see Changelog) have landed.
>
> **Superseded 2026-10-10** by "RULED 2026-10-10 — the Project menu" above: Knowledge retired into
> **Project**, and Read becomes **Page** (#5652). Items below marked **[GAP]** were proposed and never
> built (#5652).

Two domain menus (**Read**, **Knowledge**) carry the archival workflow; the rest are the macOS
standards, each cleaned to its true job. Title-case labels; verbs for actions; ellipsis where more
input is needed; toggled items use one changeable label (Show/Hide); icons only where they clarify,
uniform per group.

- **File** — get sources in and out (Parts III, IX). New Library… (no chord), Open…, Open Recent ▸, Close
  Library · New Window (**⌘N**, always a separate window), New Tab (**⌘T**, always a tab in the key
  window's tab group; macOS), Duplicate Window (#5286: the Finder and Safari grammar) · **Import ▸** (Link/Copy/Move Files…, New Folder) · **Export
  ▸** (Markdown…, Word…, BibTeX…, Markdown Static Site…) · Grant Folder Access… · Print… **[GAP]**
  (#5652; no Print… exists). *Changed 2026-10-10:* New Library… is Set Up New Project…, Close Library
  is Close Project.
- **Edit** — change the selection. Undo/Redo · Cut/Copy/Paste · Delete · Select All · Rename · Find…
  (the app's own search surfaces own ⌘F; keep the routed Select All / Undo from `MenuShortcutBoundaryTests`.)
- **View** — how it LOOKS (Part V, appearance only). As Icons/List/Columns/Gallery (⌘1–6) · **Sort By
  ▸** · **Preview ▸** (Side/Bottom/Hide, Representation) · Show/Hide Sidebar · Show/Hide Inspector
  (⌃⌘I) · Panes ▸ · **Workspaces ▸** (⌘⌥1–5, Save…, Manage…) · Enter Full Screen. (Submenus, per the
  ratified nesting.)
- **Go** — move around. Back/Forward · Enclosing Folder · Reveal in Sidebar **[GAP]** (#5652; not
  built) · recent locations.
- **Read** — the reading & annotating surface (Parts IV, VI). **Reader Lens ▸** (Content, Translation,
  Artifact…) · **Representation ▸** **[GAP]** · **Annotate ▸** (markup tools, ruler) **[GAP]** ·
  **Extract ▸** (Run OCR, Run NLP, Detect Language) **[GAP]** (#5652; none of the three exists — the
  Read menu has Reader Lens ▸, Zoom ▸ and Rotate) · Zoom (In/Out/Actual Size/Fit) · **Magnifier ▸**
  (Loupe, panel) · Next/Previous Page. Everything you do WHILE reading a source lives here, not
  scattered in View.
- **Knowledge** — **retired 2026-10-10 into Project** (see the ruling above). Making & querying meaning
  (Parts VII, VIII; the AI/data workflow). New Claim, New Entity **[GAP]** (#5652; never built) ·
  SPARQL Console… (#3298, its own window; now Project › Connect) · **Workflows ▸** (New Workflow/Chain/Comparison/
  Schedule/Trigger, Run Workflow on Selection…) · **Chat ▸** (New Chat) · **Search ▸** (Search, Saved
  Searches). "Knowledge Graph View" retired with the KG sidebar mode (#4705 increment 3). This is
  today's "Data" menu, renamed and completed to read as the meaning-making stage — and its items are
  the SAME shared `Focused*Button` components the toolbar "+" renders (no twin definitions).
- **Window / Help** — standard.

**Rationale (HIG):** every top-level menu is now a stage a user recognizes ("I'm reading" → Read;
"I'm building claims / running workflows" → Knowledge; "I'm getting things in/out" → File). Repeated
terms (Sort by…, Reader lens…, New …) collapse into submenus. Nothing is buried in a 12-section View.
Two domain menus keep the bar short (HIG: be mindful of length) while covering the whole guide.

**Alternatives to weigh:** (a) add a third domain menu **Organize** (Part V verbs: New Folder, Tag,
Move, Group) if Read+Knowledge feel overloaded; (b) keep Import under a top-level **Sources** menu
rather than File. Flagged for the CD.

**Open (per CD): per-view filters + metadata** — each view mode has its own filters/metadata; do those
get menu homes (e.g. View ▸ Filter ▸ per active view) or stay in-surface? Decide with this structure.

### Tests against THIS spec (crucial — CD)

The beachball lesson applies to menus: **test the design, not the code.** Each ruling above gets a
spec test so a regression fails CI, not the CD by hand:
- `menus.bar-structure` — **[GAP]** (#5652) a source/policy test (the `MenuShortcutBoundaryTests` shape) asserts the
  menu bar declares exactly these top-level menus and that each named command lives in its ruled
  home (e.g. Reader Lens under **Read**, New Workflow under **Knowledge**, Sort under **View ▸ Sort**),
  NOT in a generic dump. Fails if a command drifts back to the wrong menu.
- `menus.submenu-nesting` — **[GAP]** (#5652) asserts View composes its groups as `Menu` submenus (Workspaces/Sort/
  Preview/Layout), not flat sections.
- `menus.no-hand-rolled-duplicates` / `menus.data-and-plus-agree` (below) — the "+" and Knowledge
  menu render the same shared components.
- A behavior/XCUITest (the workspace-responsiveness pattern) opens each top-level menu and asserts it
  presents its ruled items and stays responsive — the runtime check structural tests can't give.

---

## Grounded in existing machinery (reviewed 2026-09-15) — build on this, do NOT invent a catalog

A code + docs + tests + agent-work review shows the app **already has** the "one source, many
surfaces" command system. The right move is to EXTEND it, not add a parallel abstraction (ponytail).

- **The idiom is house policy.** `docs/contributor_manual/swiftui-principles.md` §"Use @FocusedValue
  for Menu Commands" mandates `@FocusedValue`-routed commands (❌ NotificationCenter). Menu items are
  `Button`s that call a focused action and `.disabled` when no window publishes it.
- **Reusable command components already exist** (`App/Menus/FocusedCommands/FocusedCommandButtons+*`):
  `FocusedNewFolderButton`, `FocusedImportFilesButton` (itself a complete `Menu("Import")` with
  Link/Copy/Move), `FocusedNewChat/Workflow/Comparison/Chain/ScheduleButton`,
  `FocusedRunWorkflowOnSelectionButton`, `FocusedRenameButton`, `FocusedDeleteButton`,
  `FocusedOpenInNewTab/NewWindowButton`, `FocusedSelectAll…`. Each is a `View` wrapping one
  `@FocusedValue` action with its own label, icon, shortcut and enablement.
- **The shared-across-surfaces pattern already ships**: `ReaderExportMenuItems` renders in BOTH File ▸
  Export and the reader head's context menu — ONE definition, two surfaces. This is the template.
- **Guardrail tests already exist** to keep surfaces honest: `MenuShortcutBoundaryTests` (source-grep:
  exactly one ⌘Z owner that defers to the responder chain; no ⌘I/⌘F collisions),
  `MenuTerminologyBoundaryTests` (label consistency), `SidebarContextMenuPolicyTests` (context-menu
  verbs via pure extracted functions — never silently empty), `ReaderExportFocusedValueTests`,
  `LibraryImportFocusedValueTests`, `SelectAllRoutingPolicyTests`.
- **Prior art**: `agent-work/plans/2026-07-24-context-menu-run-workflow-targets.md` +
  `.../superpowers/specs/2026-07-24-context-menu-run-workflow-targets-design.md` (context-menu
  workflow targets) and `agent-work/status/2026-08-03-workflow-menu-vs-engine-audit.md`.

**So the "command catalog" is `FocusedCommandButtons` + the `@FocusedValue` bus, and it is already
the ratified idiom.** An `AppCommand` value type would be a NEW SYSTEM duplicating this — rejected.

## Proposed design (the better way) — adapt what exists

### 1. Dedupe onto the existing reusable components — **[PROPOSED]**

The real defect (M2) is that some surfaces render the shared `Focused*Button`s (the menu-bar "Data"
menu does) and others hand-roll raw `Button`s for the same verbs (`AddItemMenu`, several context
menus). The fix is mechanical and subtractive:

- **`AddItemMenu` (the "+")** renders the SAME `FocusedNewFolderButton` / `FocusedImportFilesButton` /
  `FocusedNewChatButton` / … the Data menu already uses — delete its hand-rolled Link/Copy/Move and
  New-X `Button`s. One definition, both surfaces (the `ReaderExportMenuItems` pattern).
- **Context menus** (row Delete/Rename/Open-in-New-Tab, pane-head Split/Close/Export) pull the same
  `Focused*Button`s / `*MenuItems` structs rather than re-authoring the verb.
- Where a verb has no reusable component yet, extract ONE (a `Focused…Button` or a `…MenuItems`
  `@ViewBuilder`), following the established shape — not a new registry.

No `AppCommand` type, no catalog object, no migration framework. Just reuse the components that exist
and extract the few missing ones in the same mold.

### 2. Natural top-level homes (macOS HIG) — **[PROPOSED]**

- **File** — library lifecycle (New/Open/Close/Save As), New/Duplicate Window, Import, Export,
  Grant Folder Access. *(Mostly already correct.)*
- **Edit** — selection & mutation: Undo/Redo, Cut/Copy/Paste, **Delete**, Select All, Rename, Find.
  Today Delete/Select-All are published per-surface via `@FocusedValue` but not gathered under Edit;
  gather them.
- **View** — appearance & layout ONLY: Sidebar mode, Library layout (⌘1–6), Preview/Representation/
  KG view mode, Inspector, Canvas, Pane visibility, chrome toggles (Workflow/Find bars). **Move Sort
  out** (to a View ▸ Sort submenu or Edit-adjacent, TBD) and **move Workspaces out** (see below).
- **Workspaces** — **[PROPOSED new top-level menu]**, or a tightened View ▸ Workspaces submenu: the
  five built-ins (⌘⌥1–5), saved workspaces (⌘⌥7–9), Save Workspace…, Manage Workspaces… It is a
  first-class concept (it rearranges the whole window) and deserves to not be buried among toggles.
  Pairs 1:1 with [[panes-workspaces]] `workspaces.one-system`.
- **Data** — the domain feature verbs (New Chat/Workflow/…, Run Workflow on Selection). This becomes
  the *single* definition; the toolbar "+" renders the SAME catalog subset instead of its own copy.
- **Go** — navigation (Back/Forward, parent, reveal). *(Exists.)*
- **Reader/Image** — the lens/zoom/export verbs stay context-published from the active pane (already
  the pattern), and also appear under View/Edit as the catalog dictates.

### 3. Contextual menus render the same components — **[PROPOSED]**

Each right-click menu declares WHICH verbs apply to the clicked target (a document row → Open,
Rename, Delete, Export, Reveal, Run Workflow On…; a pane head → Split, Close, Open in New Tab) and
renders the shared `Focused*Button` / `*MenuItems` views for them — never re-authoring the `Button`.
Change a verb's label or shortcut in its one component and every surface follows.

---

## Cross-platform (iPad / Mac / iOS) — idiomatic, one set of components — **[PROPOSED]**

The command surfaces differ by platform, but SwiftUI already routes them and the shared components
make it automatic — this is a reason to reuse, not rebuild:

- **macOS + iPad**: `Commands`/`CommandMenu` populate the menu bar (iPad shows it with a hardware
  keyboard / ⌘). `.keyboardShortcut` on the shared `Focused*Button`s lights up there for free.
- **iPhone (and iPad touch)**: no menu bar — the command surface is the **toolbar "+"/overflow and
  `.contextMenu`** (long-press). Because those render the SAME `Focused*Button`s, a verb defined once
  appears correctly whether it's a menu-bar item or a context-menu row; nothing is platform-forked
  per verb.
- **Existing compact pattern to follow, not duplicate**: the app already forks layout by width via
  `usesCompactReaderFlow` (compile-time false on macOS, true at compact width — see
  [[panes-workspaces]]). Menus follow the same rule: the component is shared; only WHICH
  container hosts it (a `CommandMenu` vs a toolbar `Menu`/`.contextMenu`) is chosen per size class.
- **Guardrail**: a verb must not exist on ONE platform only by accident. A source/policy test asserts
  each creation + selection verb has a reusable component (so both a `CommandMenu` and a
  `.contextMenu` can host it), rather than living solely inside a macOS-only `CommandMenu` body.

**Settled 2026-10-17**: iOS/iPad is a first-class target for release 1 (iOS and iPadOS 27 only; ruled in
rulings-2026-10-17). The design holds (shared components), and iOS-only tests may be written.

---

## Behaviors (each → one pinning test, extending the tests that already exist)

- `menus.no-hand-rolled-duplicates` — **[PROPOSED]** a verb that has a reusable component
  (`Focused*Button` / `*MenuItems`) is never re-authored as a raw `Button` on another surface.
  *Test:* extend `MenuTerminologyBoundaryTests` (source guardrail) to fail if e.g. `AddItemMenu`
  contains `Button("New Folder")` while `FocusedNewFolderButton` exists.
- `menus.data-and-plus-agree` — **[BROKEN]** (#4903) the menu-bar "Data"/Knowledge menu and the
  toolbar "+" should render the same creation verbs from the same components — and a guardrail
  now actually enforces this, not just proposes it: `scripts/check_action_surface_matrix.py`
  scans the real action surface and reports 14 live gaps today, including New Comparison, New
  Folder, New Schedule, New Workflow (missing BOTH a menu item and a keyboard shortcut), and Run
  Workflow on Selection (missing a menu item). Not traced to a specific commit — pre-existing.
  *Test:* the guardrail itself; extend `MenuTerminologyBoundaryTests` (source guardrail) if a
  finer-grained assertion is wanted, the `ReaderExportFocusedValueTests` shape.
- `menus.natural-home` — **[PROPOSED]** appearance/layout only under View; Sort and Workspaces are
  NOT in the View dump. *Test:* a source/policy assertion on which sections `ViewMenuCommands`
  composes (it must not compose `SortSection`/`WorkspaceCommandsSection` once re-homed).
- `menus.shortcut-uniqueness` — **[PARTIAL]** (#4894, retagged 2026-09-19 by the spec-led test
  audit: both its pinning tests read `.swift` files as text and regex-match chord literals — a
  real regression guardrail, but proof the SOURCE contains no duplicate chord literal, not proof
  a menu mounted at runtime never collides) (enforced 2026-09-16, dfa937946) no two commands share a key
  equivalent in one scope (the ⌘⌥1→loupe and double-minted ⌘⌥F "Find in Artifact"/"Find in Page"
  defects the workspace consolidation hit). *Enforced:*
  `Tests/Unit/general/Views/Shell/MenuShortcutUniquenessTests.swift` enumerates every ⌘⌥ chord the app
  mints — the workspace slots map to ⌘⌥1–5 in declaration order, all distinct, none is the loupe's
  ⌘⌥L — and a source-scan fails if any ⌘⌥ literal chord is claimed by two commands. Complements the
  older `MenuShortcutBoundaryTests` (single-owner ⌘Z, ⌘I/⌘F non-collision). **Made `#if`-aware
  2026-09-18** (see Changelog): the scan tracks `#if`/`#elseif`/`#else` branch nesting per mint and
  only flags a chord shared across branches that are NOT provably mutually exclusive, so one command
  declared once per platform branch (`#if canImport(AppKit) / #else`) is not a false collision.
- `menus.context-matches-bar` — **[PROPOSED]** (#4693) a verb in both a context menu and the menu bar is the
  SAME component (same label/icon/shortcut/enablement). *Test:* the `SidebarContextMenuPolicyTests`
  pure-function shape — assert the context menu's verb list is drawn from the shared components.
  **Ruled 2026-10-10:** every context-menu verb is also in the menu bar, through one shared component.
  *Built 2026-10-10 for Find the Documents* (`menus.project.find-the-documents-one-component`); the
  rest is #5652.
- `menus.undo-reaches-every-mutating-action` — **[BROKEN]** (#5658) superseded on 2026-10-10:
  what ⌘Z and ⇧⌘Z do is owned by `ui/undo-everywhere.md` (one helper, one step stack per window,
  the engine judging every reversal), and the undo design by `safety/undo.md`. The central seam
  this line once recorded as OK (`ActionInvokeService.invokeAction` writing every audited call
  into a per-library `LastAction`, and `UndoLastActionButton` walking `AuditStore`'s log) reverses
  the newest row of the always-there project, whoever made it and whichever project the window
  shows; that is `undo.window`, tagged BROKEN there. Its tests (`LastActionScopingTests`,
  `AuditStoreRedoTests`) are replaced in that spec's slice 1. The Edit menu's single ⌘Z owner and
  the routing ahead of the responder chain stay this spec's (`MenuShortcutBoundaryTests`).
- `menus.ipad-full-parity` — **[PARTIAL]** (#3307) built 2026-10-17 (iOS I1, unrun): the iOS App declares File, View, Go and Page from the same structs as the Mac (`FicheroApp_iOS.swift` `.commands`); Edit, Format and the app-menu extras are still Mac-only, pending the undo-gesture ruling (#5658). Test: `fichero/Tests/Unit/general/App/IOSCommandsSharedTests.swift`. Original text: iPad must expose the SAME menu-bar command set and
  the SAME contextual-menu items as macOS — no iPad-reduced subset (the maintainer's 2026-07-06 directive;
  iPhone scope is explicitly left open, undecided). Not audited this pass: no source scan was run
  against every `CommandGroup`/`.commands` definition and every `.contextMenu` for an
  `os(macOS)`-only gate that would silently exclude iPad. This spec's own "Cross-platform" section
  above already commits to the shared-component design that would make parity fall out for free
  once built — the gap is verifying/completing that build, not a design question.
- `help.save-logs-for-support` — **[PARTIAL]** (#5656; built 2026-10-10, tests written and not yet
  run — becomes **[OK]** when the manager's run passes them) **Help › Save Logs for Support…**, in the
  dev feature tier only (`SupportLogs.isOffered(for:)`), sits after the User Manual link. It saves
  one zip, `Fichero Logs <yyyy-MM-dd HH.mm>.zip`, through a save panel that starts on the Desktop
  (so the sandbox grants the write), then reveals it in Finder. The zip holds everything under the
  app's `Library/Logs/Fichero` as the sandboxed app sees it (engine.log capped to its last 20 MB,
  starting on a whole line) plus `about.txt`: version and build, feature tier, macOS version, model
  identifier, memory, free disk, date, and the logs folder (or that it was not found). A failure
  shows in an alert. App-side by design, an exception to "logic in the engine": it is needed
  when the engine is not running. *Test:* `Tests/Unit/general/App/SaveLogsForSupportTests.swift`
  (the collector against a temp logs folder with an over-cap engine.log; the tier gate; a source
  read that the Help group mounts the item behind the gate).
- `help.email-logs-for-support` — **[GAP]** (#6171; owner ask 2026-10-26) **Help › Email Logs for Support…**, beside Save Logs, composes a new email to the support address the About window shows with the same zip attached (`help.save-logs-for-support` builds it): the app's logs, the ENGINE log (`engine.log`, last 20 MB) and the server's own logs, plus `about.txt`. The mail is only composed, never sent: the person reads it and presses Send. Where no mail account is set up, it saves the zip as Save Logs does and says where it is, with the address to send it to. Offered in every tier, not only dev, because the people who hit a crash are not on the dev tier (this reverses `help.save-logs-for-support`'s dev-only gate for the email item; the person sees what is attached before sending). *Test:* `Tests/Unit/general/App/EmailLogsForSupportTests.swift` (the attachment is the collector's zip; no mail account falls back to a saved zip; the item is mounted in every tier).
- `help.send-logs-to-the-maintainer` — **[PARTIAL]** (owner 2026-10-30; folds `help.email-logs-for-support` #6171, which asked the same of the About window's address) **Help › Send Logs to the Maintainer…**, beside Save Logs for Support… (which stays, dev tier only), offered in EVERY tier. Choosing it first shows what the zip contains and asks: the app's logs folder (`Library/Logs/Fichero`; the engine log cut to its last 20 MB), and `about.txt` (version, build, tier, macOS, model, memory, free disk, date, the logs folder), and says the logs can name files the app opened; nothing is sent until the person has read it and chosen Continue. Continue builds the same zip as Save Logs into a temporary folder and hands it to `NSSharingService(named: .composeEmail)` with the zip attached: the mail is composed, never sent. With no mail account (`canPerform` false) it falls back to the Save Logs panel, so the person can send the zip by hand. The zip holds nothing outside the logs folder plus `about.txt`: the collector skips anything that could be a library database or a credential (`*.duckdb`, `*.db`, `*.sqlite`, `*.fichero`, `.api-key`, names containing `token`, `credential`, `secret` or `password`, `*.pem`, `*.key`), and `about.txt` carries no token, no library path and no username (the logs folder is written with `~` for the home folder). The temporary folder holding the zip is removed when the share ends or fails, and any left by a quit mail is removed at the next send. **[GAP] address to be set:** no support address exists in the repo (the About window shows none; searched `support@`, `mailto`), so the draft's `To` is empty and the person addresses it; the owner supplies the address, one constant in `SupportLogs.maintainerAddress`. *Test:* `Tests/Unit/general/App/SendLogsToMaintainerTests.swift` (the archive's file list is the logs folder's files plus about.txt only; a library database and credential files placed in the folder are left out; about.txt has no token and no library path; the confirmation text names every part of the zip; the item's mount outside the tier gate is asserted in `SaveLogsForSupportTests.testHelpMenuMountsSendLogsInEveryTier`). Written 2026-10-30 WITHOUT building: nothing here has been compiled or run in Xcode (only the exclusion rule was run in a bare `swiftc` check); the address is still **[GAP]**, and the no-mail-account fallback to the Save Logs panel is untested by a unit test (it needs a Mac with no mail account).

---

- `menus.one-command-table` — **[GAP]** (#6435; owner 2026-11-08) every command has ONE row in one table (section 2 of the 2026-11-08 review): its menu-bar group, the surfaces it applies to, its component, chord and icon; the menu bar and every surface's context menu render the table's rows for that surface, in its order, through the same component, so a context menu never holds an item the table does not and never lacks one it does. Acceptance: for each surface, the rendered context menu's titles equal the table's rows for it; the menu bar's groups equal the table's groups. *Test:* `MenuTableTests.swift` (not yet written; the table as a value, the per-surface equality, every row has a group, every chord in the table is unique).
- `menus.chords-are-standard-mac` — **[GAP]** (#6435; owner rule 2026-11-08) every chord is a logical standard Mac chord: Apple's convention where one exists (⌘N, O, W, S, Z, X, C, V, A, F, G, ⌘, Settings, ⌘[ ⌘] Back/Forward, ⌘⌫ Delete, ⌘0 Actual Size, ⌥⌘I Inspector), a standard chord is never repurposed, and a new command's chord follows the pattern of its family (⌥ or ⇧ variants of the related command, mnemonic letters); the 2026-11-08 audit (section 4) lists the chords to change, and `MenuShortcutUniquenessTests` gains a standard-chord table so a repurposed standard fails the test. Acceptance: ⌘I is not Link Files, Back is ⌘[, the Inspector is ⌥⌘I, Rotate is ⌥⌘← / ⌥⌘→, and every proposed Segments and Levels chord is the settled one. *Test:* the existing `MenuShortcutUniquenessTests.swift` extended with the standard-chord table.
- `menus.toolbars-one-home-per-tool` — **[GAP]** (#6435; owner addition 2026-11-08) toolbars hold tools and view switches, never a selection's verbs; every tool has ONE home (the Preview's Editing bar for image and shape tools, the Reader bar for display and navigation, the Workflow bar for the chain) and a per-pane tool never appears in the window toolbar; the Source pane image controls (Enhance, Clean up the folder) leave for the Edit pane (#6436) and the two Edit Segments toggles go (`source/segment-editor-crud.md` Step 1.7). Acceptance: no toolbar shows Enhance outside the Edit pane; no control is called Edit Segments; every tool appears in exactly one bar. *Test:* `ToolbarHomesTests.swift` (not yet written; the tool-to-bar table, each tool once).
- `menus.less-text-more-indicator` — **[GAP]** (#6435, #6441; owner 2026-11-08: the whole app is too discursive) ONE rule for every surface — labels, table rows, alerts, sheets, empty states, help text, tooltips, settings: say it with an INDICATOR where one says it (a state glyph, a spinner, a progress bar, a count with a unit, a badge), and with the FEWEST words where words are needed: a label is a noun or an imperative verb phrase of at most four words, never a sentence; a settings row is a label and at most ONE sentence under it; an alert is a title of at most eight words, at most one sentence of body, and its buttons are the verbs ("Download", "Add Key…", "Delete", never "OK"/"Yes"); an empty state is one line or nothing (`activity.window.no-empty-prose`); a help text is at most two sentences and links to the manual for more; a tooltip is the label's long form, at most eight words; no "Successfully", "Currently", "Please", "Note that", no exclamation marks; a timestamp is written as text only where no bar or glyph can say it, and once. The rule is a TEST over the string catalogue and the row models (word counts, forbidden words, one sentence per settings row), reviewed with the wording pass of Step 2.5, so a discursive string fails the gate. Acceptance: every menu title, settings label and alert title in the catalogue passes the counts; an alert with two body sentences fails the test; the Activity row model's strings pass `activity.pane.text-budget`. *Test:* `LessTextMoreIndicatorTests.swift` (not yet written; the catalogue and the row models against the budgets and the forbidden words), the existing `MenuShortcutUniquenessTests.swift` as the pattern of a rule-as-test.
- `menus.wording-and-icons-one-rule` — **[GAP]** (#6435) every command's title is an imperative verb, names its object when the object is not the selection ("Run the Recipe on This Folder…", "Delete 3 Segments"), ends with an ellipsis when a sheet follows, and carries ONE icon used everywhere it appears; the table is the source and the test reads it. Acceptance: no two rows of the table name one command differently; every row with a sheet ends in an ellipsis; every icon appears for one command only. *Test:* `MenuTableTests.swift` (not yet written; the wording and icon rules over the table).
- `menus.context-menus-mirror-the-table` — **[GAP]** (#6435) a context menu is the table's rows for its surface and nothing else; the Library's `documentContextMenu`, the sidebar's row menus, the Preview's region menu, the Reader's line menu, the Segments pane's and the Inspector's menus all render from the one table (one component per row, as the item verbs already are); hand-rolled items go. Acceptance: right-clicking a page in the sidebar, the list, the Preview and the Reader shows the same rows for a page, in the same order with the same icons. *Test:* `MenuTableTests.swift` (not yet written).

## RATIFIED 2026-09-15 (evening, CD)

- **View is organized into SUBMENUS, not flat sections.** The junk-drawer fix is nesting: each group
  becomes a flyout — **View ▸ Workspaces ▸** (⌘⌥1–5 + Save/Manage), **View ▸ Sort ▸**, **View ▸
  Preview ▸**, **View ▸ Layout ▸**, etc. — so opening View shows a short list of submenu titles
  instead of ~12 stacked sections. "They should all be submenus — not Workspaces [inline] but
  Workspaces ▸ …". Workspaces stays under View (not a new top-level menu; Xcode-style top-level was
  considered and declined). The keyboard shortcuts (⌘⌥1–5, ⌘1–6, ⌃⌘I) live on the leaf items inside
  the submenus, so muscle memory is unchanged.
- **Platform = iPad / Mac / iOS first-class NOW.** Build and test the command surfaces on all three,
  not Mac-first. The shared `Focused*Button` / `*MenuItems` components render in a `CommandMenu`
  (Mac / iPad menu bar) or a toolbar `Menu` / `.contextMenu` (iPhone) unchanged; tests cover each
  platform's surface. This raises the bar on every menu change — no macOS-only command bodies.


## Review 2026-11-08 — every menu, context menu, toolbar and chord (Fable, for #6435; the manager reads before approval)

Read from the code at origin/integration (`fichero/fichero/App/Menus/**`, every `.contextMenu` under `Views/`, `Views/Shell/Toolbar/*`, `Views/Shell/PaneHead/*`, `Views/Reader/ReaderToolbar*`, every `keyboardShortcut(`). Spec work only. Folds in Edit › Segments ▸ (`source/segment-editor-crud.md` Step 1.2, `menus.edit.segments-submenu`), Group/Ungroup (Step 1.16), Run the Recipe on This Item (Step 1.1 below, #6411), the focused-pane Select All (`source/segment-editor-crud.md` Step 1.10) and the owner's chord rule of 2026-11-08 (logical, standard Mac chords; never repurpose a standard one; new chords follow the pattern).

### 1. Inventory: what exists

**Menu bar** (`FicheroApp.swift` CommandGroups, `App/Menus/*`): Fichero (About replaced, Settings ⌘,, Quit group) · **File** (`FileMenuCommands.swift`: Set Up New Project…, Connect to Library…, Open… ⌘O, Open Recent ▸ with Clear Menu, Close Project ⌃⌘W, New Window ⌘N, New Tab ⌘T, Duplicate Window ⇧⌘T, Import ▸ Link Files… ⌘I / Copy Files… ⌥⌘I / Move Files… ⇧⌘I (`+SidebarActions.swift`), New Folder ⇧⌘N, Save Project As… ⇧⌘S, Export ▸ BibTeX…, Markdown Static Site…, Export Page As ▸ Markdown…/Word…, Import Page From… (`ReaderExportCommands.swift`), Grant Folder Access…) · **Edit** (Undo ⌘Z / Redo ⇧⌘Z routed, `+UndoNavigation.swift`; Select All ⌘A routed by the focused pane, `+SelectAll.swift`; Rename ⏎-when-focused, Delete ⌘⌫, the item verbs Bookmark…, Add to Workspace…, Export a Copy…, Exclude ▸ (`ItemVerbs/+ItemVerbs.swift`); Proposed Document ▸ and Direction ▸ (`+ProposalVerbs.swift`); Find in Page ⌥⌘F; Page › Segments' items are moving here, `menus.edit.segments-submenu`) · **View** (`ViewMenuCommands.swift` and its sections: Library layouts ⌘1–6; Sidebar ▸ modes Library/Chat/Workflows/Automation/Research with numbers (`SidebarMode.shortcutNumber`, ⌃⌘); Sort ▸ Ascending/Descending and the fields; Preview ▸ modes ⌃⌘J/B/H and Representation ▸ ⌃⌥⌘<key>; Show/Hide Inspector ⌃⌘I; Canvas ▸; Panes ▸ (Show Mini Toolbar, pane toggles, Workflow Bar ⇧⌘G); Workspaces ▸ ⌥⌘1–5, Save Workspace…, Delete Workspace ▸, Toolbar Buttons ▸; Show Ruler; Go Up; Show Workflow Bar, Bar Labels) · **Go** (`ViewMenuPaneSections.swift:186`: Back ⌘' and Forward ⇧⌘' (`+UndoNavigation.swift`), Go Up) · **Page** (`PageAndProjectMenuCommands.swift:24`: Reader Lens ▸ (`ReaderLensSection.swift`), Next/Previous Doubtful Word ⌃⌘G / ⇧⌃⌘G, Zoom ▸ Actual Size ⌘0 / Zoom to Fit ⌘9 / In ⌘+ / Out ⌘− (`ImagePreviewMenuCommands.swift`), Magnifier Panel ⇧⌘M, Lock Magnifier ⌥⌘M, Magnifier Zoom ⌥⌘] / ⌥⌘[, Loupe ⌥⌘L, Lock Loupe ⇧⌘L, Loupe Zoom ⌃⌘] / ⌃⌘[, Rotate Left ⌘L / Right ⌘R (`RotateImageCommands.swift`), Group/Ungroup of pages (`RotateImageCommands.swift:61`), Segments section: Edit Segments, Delete, Join ⌘J (becomes ⌥⌘J, section 4), Kind/Direction/Furniture (`SegmentMenuCommands.swift`), Page › Segments › Open / Correct This Line… / Delete Lines / Create Named Order (`+LineVerbs.swift`)) · **Project** (`PageAndProjectMenuCommands.swift:52`: Set Up… / Set Up Fichero…, Start ⇧⌘⏎, Cloud switch, Edit Document Types…, Read › Reading ▸ Run the Recipe on This Folder… and Run a Step Again on This Folder ▸, Organise › Find the Documents ⇧⌘D, Connect › SPARQL Console…, Train › Train a Model… and Make Available in Every Project, Activity ▸ (run buttons), Workflows ▸ (Run Workflow on Selection… ⇧⌘R, New Workflow ⌃⇧⌘N, New Chain, New Comparison), Chat ▸ (New Chat ⌃⌘N, Add to Chat), Rename/Share/Delete Project…, Show in Finder (`+ProjectVerbs.swift`)) · **Canvas** (`CanvasMenuCommands.swift`: Zoom to Fit ⌘9, Jump Back ⌘[, Jump Forward ⌘]) · **Window** (system, Activity ⌥⌘0, tabs) · **Help** (Save Logs for Support…, Send Logs to the Maintainer…, Language Coverage…, Feature Tiers…).

**Context menus by surface** (every `.contextMenu` under `Views/`):
- *Sidebar rows* (`Sidebar/ItemRow/SidebarItemRow+Presentation*.swift`, `SidebarItemContextMenu.swift`, `SidebarView+ViewComponents.swift:111` for the always-there project, `Sections/LibraryHeaderRow.swift`, `SidebarModelsNode.swift` Train a Model / Make Available, `Trash/SidebarTrashNode.swift` Put Back, `Sharing/HostGoneRowView.swift` Forget): New Folder, Share…, Rename, Duplicate, Make Alias, Delete ⌘⌫, Reveal Original, Exclude ▸, Bookmark…, Add to Workspace…, Find the Documents, Run the Recipe on This Folder…, Export a Copy…, Run Workflow ▸, Add to Chat, Move to Folder ▸, Automation verbs.
- *Library item list, every mode* (`Library/LibraryView+ContextMenu.swift` `documentContextMenu`, rendered by List, Table, Columns, Icon, Canvas 2D/3D, Dataset grid/cards/map/timeline/calendar, `ProposedDocumentsInItems.swift`, `TrashPane.swift`, `NoteListView.swift`, the empty-area Import menu): Open/Quick Look, Add to Chat, Import Files Here…, New Folder, Rename, Duplicate, Make Alias, Export a Copy…, Reveal Original, Locate Originals…, Add to Workspace…, Bookmark…, Find the Documents, Run the Recipe on This Folder…, Group as Stack / Ungroup, Exclude ▸ (processing, search, everywhere), Direction ▸, Delete, Run Workflow ▸; Trash: Put Back, Empty Trash…; Notes: Open in Window, Delete.
- *Preview image* (`Preview/ImageViewer/Regions/ZoomableImagePreviewMac+Regions.swift:180` `regionContextMenu`: Add Region… / Stop Adding Regions, Clear Selections, New Region from Selection… (gated)); *Preview PDF page* (`PDFViewer/PDFPageWithToolbar.swift:397`); the Regions layer's double-click popover (`+SegmentPopover.swift`).
- *Reader* (`Reader/Page/ReaderLinesView.swift:105`: Correct This Line…, Delete; `ReadingPaneView.swift:512`: the lens items; `Components/ReadingOrderList.swift:80, 215` `lineMenu`: Correct This Line…, Delete, Create Named Order; keys ⌥⌘↑↓⇞⇟ when the list is focused, `ReadingOrderListKeys`).
- *Segments pane* (`Segments/SegmentsPictureGrid.swift:86`: Open; `CorrectThisLine.swift:102`: Correct This Line…).
- *Inspector* (`Inspector/Artifacts/ArtifactListView.swift:248, 353`: Run Workflow, Open in Window, Set as Document Content, Translate ▸; `Source/Info/…BibliographyRow.swift`: Edit…, Resolve Metadata, Delete Reference…; `Document/DocumentInspectorRelatedTab.swift`: Open Document; `Notes/Annotations/AnnotationListView.swift`: Open in Window; `Knowledge/*`: Copy all keywords, claim and entity menus, Delete; `Citations/CitationListView.swift`: Open in Window).
- *Pane head and crumbs* (`Shell/PaneHead/PaneHead.swift:132, 241`: the crumb path, pane rows); *bars* (`Shell/Toolbar/WorkflowBar.swift:285`, `AnnotationBar.swift:40`: Bar Labels; `WorkflowBar+ChainRail.swift:244`: Choose Model…); *Activity* (`Activity/Window/ActivityGroupsView.swift:89`: Stop, Show Details, Delete N Runs; `ActivityViewHelpers.swift:157`); *Workflow* (`Workflow/**`: node, edge, list, chain, batch and execution menus: Delete Connection, View Details, Resume, Delete Batch, New Chain); *Chat/Research* (`Chat/Research/ResearchProjectListView.swift`: Delete Project).

**Toolbars** (controls by file; counts are `help`/`accessibilityLabel` lines): the window toolbar (`Shell/Toolbar/ActivityStatusToolbarItem.swift`, `PaneHead/PaneKindSelector.swift`, `PaneChromeMenu.swift`); the **Workflow bar** (`WorkflowBar.swift`, `+ChainRail`, `+ChainRow`, `+Compare`, `+Context`, `WorkflowStepInspectPopover.swift`: a chain rail with per-step model choice and compare); the **Annotation bar** (`AnnotationBar.swift`: Tag Next Highlight…, Clear Pending Tags, labels); the **Preview head controls** (`PaneHead/PreviewHeadControls.swift`: up to the parent image, previous/next page, previous/next rendition, Renditions ▸, show/hide zoom controls ⌥⌘E, Edit Segments); the **Preview markup tools row** (`PaneHead/PreviewMarkupToolsRow.swift`: Highlight ⌥⌘Y and its colour/mode, the tools with ⌥⌘ letter chords u, v, w, r, g, s, k, n, the Shape kind picker, Join N); the **Reader toolbar** (`Reader/ReaderToolbar.swift`, `+Controls`, `+Overflow`, `ReaderToolbarCluster.swift`: close, pages, renditions, zoom in/out/fit/actual, magnifier, loupe and lock, Edit image and the image tools, pin, the Display menu: Show Image/Annotations/Word Boxes/Regions/Text Inline/Edit Segments, Filter, Show metadata); the **Source pane image controls** (`Preview/SourcePaneImageControls.swift`: Enhance, Clean up the folder; the toolbar #6436 says leaked); the **Set Up** window's own buttons (Compare on These Pages, Run this step, Find a Reader…, `Onboarding/*`).

**Chords, complete** (owner × key): standard and kept: ⌘O Open, ⌘N New Window, ⌘T New Tab, ⌘W/⌃⌘W Close, ⌘Z/⇧⌘Z, ⌘A, ⌘F Find (library search), ⌘⌫ Delete, ⌘, Settings, ⌘0 Actual Size, ⌘+/⌘−, ⌘1–6 layouts (Finder's ⌘1–4 pattern), ⌥⌘1–5 workspaces, ⇧⌘S Save As, ⇧⌘N New Folder. Non-standard or repurposed (section 4): ⌃⌘I Inspector (Xcode's pattern; the Finder convention is ⌥⌘I Show Inspector, and section 4 changes it), ⌘I Link Files (⌘I is Get Info everywhere), ⌥⌘I / ⇧⌘I Copy/Move Files, ⌘L Rotate Left (⌘L is Location in browsers and Finder's Make Alias), ⌘R Rotate Right (⌘R is Reload/Reply), ⌘J Join (⌘J is Jump to Selection / Show View Options), ⌘9 Zoom to Fit (twice: Page and Canvas), ⌘' / ⇧⌘' Back/Forward (Go) beside ⌘[ / ⌘] Jump Back/Forward (Canvas) and ⌘[ / ⌘] in the Set Up pager, ⇧⌘T Duplicate Window (⇧⌘T is Reopen Closed Tab), ⇧⌘D Find the Documents (⇧⌘D is Send in Mail; ⌘D Bookmark), ⇧⌘R Run Workflow on Selection, ⇧⌘⏎ Start, ⌃⌘N New Chat, ⌃⇧⌘N New Workflow, ⌃⌘G / ⇧⌃⌘G Doubtful Word, ⇧⌘M / ⌥⌘M Magnifier, ⌥⌘L / ⇧⌘L Loupe, ⌥⌘[ ] and ⌃⌘[ ] magnifier and loupe zoom, ⌥⌘E zoom controls, ⌥⌘Y Highlight, ⌥⌘U/V/W/R/G/S/K/N markup tools, ⌥⌘F Find in Page, ⇧⌘G Workflow Bar (⇧⌘G is Find Previous), ⌃⌘J/B/H Preview modes, ⌃⌥⌘<key> Representation, ⌃⌘1–5 sidebar modes, ⌥⌘0 Activity, ⌃⌘R (ContentView root layout), ⌥⌘↑↓⇞⇟ order moves, ⌥⇧⌘W (`ViewMenuPaneSections.swift:306`). Proposed and provisional until this table settles them: ⌥⌘A Select All Segments, ⌥⌘N New Region, ⌥⇧⌘N New Line, ⌥⌘S Split, ⌥⌘G / ⌥⇧⌘G Group/Ungroup, ⌥⌘⏎ Run next step, ⌥⌘R Run the Recipe on This Item, ⌥⌘↑/↓ levels, ⌥⇧⌘W Use as Working Text, ⌥⌘L Compare Levels, Edit Shape's free chord, Run Again (#6437).

### 2. The ONE command table

Every command has one row: one logical group (its menu-bar home), the surfaces it applies to (and so the context menus that render it), one component, one chord or none, one icon. A command appears in the context menu of EVERY surface it applies to and nowhere it does not; the menu bar and the context menus render the same component (`menus.context-matches-bar`, `menus.no-hand-rolled-duplicates`). Surfaces: **S** sidebar rows, **L** library item list (every mode), **P** Preview (image and PDF), **R** Reader, **G** Segments pane, **I** Inspector, **A** Activity, **W** workflow surfaces. Chords here are the SETTLED proposals of section 4; "—" is deliberately none.

| Group (menu-bar home) | Command | Surfaces | Chord | Icon |
|---|---|---|---|---|
| File | Set Up New Project…, Connect to Library…, Open…, Open Recent ▸, Close Project, New Window, New Tab, Duplicate Window, Save Project As…, Grant Folder Access… | — (window-level) | ⌘O, ⌃⌘W, ⌘N, ⌘T, ⌥⌘N→ see note, ⇧⌘S | system |
| File › Import ▸ | Link Files…, Copy Files…, Move Files…, Import Page From… | S, L (empty area and folder rows) | none (⌘I is Get Info and leaves) | `square.and.arrow.down` |
| File › Export ▸ | Export a Copy…, Export Page As ▸, BibTeX…, Static Site… | S, L, R | ⇧⌘E Export a Copy (the Export pattern) | `square.and.arrow.up` |
| File | New Folder | S, L | ⇧⌘N | `folder.badge.plus` |
| Edit | Undo, Redo, Cut, Copy, Paste | all | ⌘Z, ⇧⌘Z, ⌘X, ⌘C, ⌘V | system |
| Edit | Select All (the focused pane's things; the sidebar refuses) | L, P, R, I, G | ⌘A | — |
| Edit | Rename | S, L, I rows | ⏎ when a row is focused | `pencil` |
| Edit | Delete / Move to Trash | S, L, A, W, I rows | ⌘⌫ | `trash` |
| Edit | Duplicate, Make Alias | S, L | ⌘D Duplicate (Finder), ⌃⌘A Make Alias (Finder) | `plus.square.on.square`, `arrowshape.turn.up.right` |
| Edit | Bookmark…, Add to Workspace… | S, L | — | `bookmark`, `square.grid.2x2` |
| Edit › Exclude ▸ | from processing, from search, everywhere | S, L | — | `eye.slash` |
| Edit › Direction ▸, Proposed Document ▸ | the item verbs' submenus | L | — | — |
| Edit › Segments ▸ | Select All Segments, New Region, New Line, Edit Shape, Split…, Join, Group, Ungroup, Kind ▸, Direction ▸, Furniture, Delete, Correct This Line…, Create Named Order, Run <next step> on This | P, R, G, I (every segment surface) | see section 4 | per `source/segment-editor-crud.md` |
| Edit | Find in Page | R, P | ⌥⌘F | `magnifyingglass` |
| View | Library layouts, Sidebar ▸, Sort ▸, Preview ▸, Inspector, Panes ▸, Workspaces ▸, Ruler, Workflow Bar, Reading Level ▸ (#6429) | — | ⌘1–6 layouts, ⌃⌘1–5 sidebar modes, ⌃⌘J/B/H Preview modes, ⌥⌘I Show/Hide Inspector (the Finder convention; changed from ⌃⌘I, section 4), ⌥⌘1–5 workspaces, Reading Level ⌃⌥⌘↑/↓ | — |
| Go | Back, Forward, Enclosing Folder (Go Up), Reveal in Sidebar | all | ⌘[ , ⌘] , ⌘↑ (Finder) | system |
| Page | Reader Lens ▸, Zoom ▸ (Actual Size, Fit, In, Out), Magnifier ▸, Loupe ▸, Rotate Left/Right, Next/Previous Page, Next/Previous Doubtful Word, Renditions ▸, Use for Reading (#6414) | P, R | ⌘0 Actual Size, ⌘9 Zoom to Fit (Page keeps it; the Canvas duplicate goes), ⌘+/⌘−, Loupe ⌥⌘L and Lock Loupe ⇧⌘L kept, Magnifier ⇧⌘M/⌥⌘M kept, Rotate Left ⌥⌘← and Rotate Right ⌥⌘→ (from ⌘L/⌘R, section 4), Doubtful Word ⌃⌘G/⇧⌃⌘G kept | — |
| Project | Set Up…, Start, Run the Recipe on This Item (#6411), Run Again (#6437), Run a Step Again ▸, Find the Documents, Train a Model…, Make Available in Every Project, SPARQL Console…, Workflows ▸, Chat ▸, Rename/Share/Delete Project…, Show in Finder | S, L (the recipe items on every row kind) | ⇧⌘⏎ Start kept, ⌥⌘R Run the Recipe on This Item, ⌥⇧⌘R Run Again, ⇧⌘D leaves (Find the Documents: none) | `play.rectangle`, `arrow.clockwise` |
| Window | Activity, tabs, workspaces windows | — | ⌥⌘0 kept | — |
| Help | Save Logs…, Send Logs…, Language Coverage…, Feature Tiers… | — | — | — |

Items that MOVE: Page › Segments → Edit › Segments ▸ (ruled); Canvas › Jump Back/Forward → Go › Back/Forward (one history, `source.editor.select-takes-you-there-and-back`); Group/Ungroup of pages (`RotateImageCommands.swift:61`) → the Library's Group as Stack / Ungroup under Edit, beside Edit › Segments ▸ Group of segments, with different names ("Group as Stack" for pages, "Group" for segments); Rotate out of Page's chord slots (section 4); Find the Documents keeps its Project home and loses its chord; the Reader's Correct This Line… and Create Named Order join Edit › Segments ▸ as its last rows; the Source pane's Enhance and Clean up the folder leave their own toolbar for the Edit pane (#6436).

### 2b. Less text, more indicator (owner, 2026-11-08; app-wide)

The owner's feedback on Activity (too many clocks, too much text) is a rule for the WHOLE app, carried by `menus.less-text-more-indicator` and checked by one test over the string catalogue and the row models: glyph, spinner, bar, count or badge before words; a label at most four words; one sentence under a settings row; an alert title at most eight words with verb buttons; empty states one line or nothing; tooltips at most eight words; no filler words; a timestamp as text only where nothing else can say it. Activity applies it first (`activity-pane.md` Step 1.7: one glyph per state, four default columns, the error row as a red X with a short line and the refusal's fix buttons, a text budget per row); the wording pass of Step 2.5 applies it to every menu title and every alert.

### 3. Grouping rules

1. **File** opens, closes, imports and exports; it never changes a selection's content. **Edit** changes the selection (and holds every submenu that acts on a selection: Segments ▸, Exclude ▸, Direction ▸). **View** changes how the window looks and what is shown, never the data. **Go** moves (one history for every jump). **Page** acts on the page being read (zoom, lens, magnifiers, rotation, renditions). **Project** runs and sets up the recipe and the project-wide tools. **Window** and **Help** are the system's.
2. A command lives in ONE group; a surface's context menu shows the rows of the table whose Surfaces column names it, in the table's order, with the same titles, icons and chords, through the same component; a context menu never holds an item the table does not, and an item the table gives a surface is never missing from it (`menus.context-matches-bar` made testable: the table is a Swift value the menus and the test read).
3. Submenus only where a term repeats (Import ▸, Export ▸, Exclude ▸, Segments ▸, Zoom ▸, Workspaces ▸), one level deep, at most about eight items; a disabled item says why under it (`menus.disabled-says-why`, the Page › Segments precedent).
4. Wording: verbs in the imperative, the object named when it is not the selection ("Run the Recipe on This Folder…", "Delete 3 Segments"), an ellipsis when a sheet follows; one icon per command, the same everywhere.
5. Toolbars hold TOOLS (a state the pointer is in) and view switches, never commands that belong to a selection: a selection's verbs are in Edit and the context menus. Each tool has ONE home: the Preview's Editing bar for image and shape tools (`source.editor.two-bars-reader-and-editing`), the Reader bar for display and navigation, the Workflow bar for the chain; a per-pane tool never leaks into the window toolbar. Leaked today: the Source pane image controls (Enhance, Clean up the folder; #6436), the two Edit Segments toggles (head controls and Display menu; `source/segment-editor-crud.md` Step 1.7).

### 4. Chord audit (the owner's rule 2026-11-08: standard Mac chords; never repurpose a standard one; new chords follow the pattern)

**DECIDED 2026-11-08 15:45 (owner): the audit is accepted in full** — Import loses ⌘I; Rotate Left/Right become ⌥⌘← / ⌥⌘→; Inspector becomes ⌥⌘I; Back/Forward become ⌘[ / ⌘]; Join is ⌥⌘J; Duplicate Window, Find Documents, Workflow Bar and Run Workflow lose their chords. Step 2.3 builds exactly this table; nothing in it is provisional any more.

| Chord | Today | Standard meaning | Verdict |
|---|---|---|---|
| ⌘I | Link Files… | Get Info (Finder, everywhere) | CHANGE: Import loses its chords; ⌘I is reserved for a future Get Info (the Inspector) |
| ⌥⌘I, ⇧⌘I | Copy / Move Files… | ⌥⌘I Show Inspector (Finder) | CHANGE: none; ⌥⌘I becomes Show/Hide Inspector (moved from ⌃⌘I) |
| ⌘L | Rotate Left | Location (browsers), Make Alias (Finder) | CHANGE: Rotate Left ⌥⌘← and Rotate Right ⌥⌘→ (Preview.app's pattern is ⌘L/⌘R, but ⌘R collides below; one pair, arrows) |
| ⌘R | Rotate Right | Reload / Reply | CHANGE as above |
| ⌘J | Join | Finder: Show View Options; Mail and TextEdit: Jump to Selection | CHANGE (ruled 2026-11-08 by the owner's rule, the manager): Join is **⌥⌘J**, the Segments ▸ ⌥ family; ⌘J is a standard chord and leaves; the uniqueness test's standard-chord table pins it and the manual follows; supersedes the 2026-09-28 ruling that gave Join ⌘J |
| ⌘9 | Zoom to Fit (Page AND Canvas) | none; Zoom pattern is ⌘0 actual, ⇧⌘0 fit (Xcode, Preview uses ⌘9 Zoom to Fit) | KEEP one owner: Page's; Canvas's duplicate goes (the Canvas is a Library mode, View › Zoom to Fit uses the same item) |
| ⌘' / ⇧⌘' | Back / Forward (Go) | none | CHANGE to ⌘[ / ⌘] (Finder, Safari); Canvas Jump Back/Forward merges into them; the Set Up pager keeps ⌘[ ⌘] inside its own window |
| ⇧⌘T | Duplicate Window | Reopen Closed Tab | CHANGE: none (menu only) |
| ⇧⌘D | Find the Documents | Send (Mail), Add Bookmark ⌘D | CHANGE: none |
| ⇧⌘R | Run Workflow on Selection… | Reload ignoring cache | CHANGE: none; Run Again takes ⌥⇧⌘R |
| ⇧⌘⏎ | Start | none (Send in Messages is ⏎) | KEEP |
| ⌃⌘N, ⌃⇧⌘N | New Chat, New Workflow | none | KEEP (the New pattern with ⌃) |
| ⌃⌘G, ⇧⌃⌘G | Next/Previous Doubtful Word | ⌘G Find Next | KEEP (the Find pattern with ⌃) |
| ⇧⌘M, ⌥⌘M | Magnifier Panel, Lock Magnifier | ⌘M Minimise; ⇧⌘M none | KEEP |
| ⌥⌘L, ⇧⌘L | Loupe, Lock Loupe | none | KEEP; Compare Levels does NOT take ⌥⌘L (section 1's proposal withdrawn) |
| ⌥⌘[ ], ⌃⌘[ ] | magnifier / loupe zoom | ⌘[ ] Back/Forward | KEEP (modified variants of the bracket pair) |
| ⌥⌘E | Show/hide zoom controls | none | KEEP; Edit Shape takes another |
| ⌥⌘Y and ⌥⌘U/V/W/R/G/S/K/N | markup tools | none | KEEP as the tools' family; ⌥⌘N New Region COLLIDES (tool key n): New Region becomes ⇧⌘N's sibling ⌥⇧⌘N… see Segments row |
| ⌥⌘F | Find in Page | none (⌘F Find) | KEEP |
| ⇧⌘G | Workflow Bar | Find Previous | CHANGE: none (View menu only) |
| ⌃⌘I | Inspector | none (Finder ⌥⌘I) | CHANGE to ⌥⌘I |
| ⌃⌘J/B/H, ⌃⌥⌘<key>, ⌃⌘1–5 | Preview modes, Representation, Sidebar modes | none | KEEP (the View family with ⌃) |
| ⌥⌘0 | Activity | none | KEEP |
| ⌃⌘R | root layout (`ContentView+RootLayout.swift:134`) | none | VERIFY its label; drop if it is a dead item |
| ⌥⇧⌘W | `ViewMenuPaneSections.swift:306` | ⌥⌘W Close All | VERIFY; drop |
| **Segments ▸ (settled proposals)** | Select All Segments | — | ⌥⌘A outside the Reader (⌘A inside) |
| | New Region / New Line | — | ⌥⌘N collides with the markup tool n: New Region ⌃⌘N collides with New Chat; so **New Region ⇧⌘N** is wrong too (New Folder). Settled: New Region and New Line have NO chord; the tools R and L on the Editing bar make them (`source.editor.labelled-shape-tools`) |
| | Edit Shape | — | E on the Editing bar; menu chord none |
| | Split… | — | ⌥⌘S? ⌘S is Save; the ⌥ variant is free: KEEP ⌥⌘S |
| | Join | — | ⌥⌘J (ruled 2026-11-08; ⌘J leaves) |
| | Group / Ungroup (segments) | — | ⌥⌘G / ⌥⇧⌘G (Group as Stack for pages has none) |
| | Delete | — | ⌘⌫ (Edit › Delete, one keyed home); ⌫ on a surface |
| | Run <next step> on This | — | none (menu); Run the Recipe on This Item ⌥⌘R; Run Again ⌥⇧⌘R |
| **Levels (#6429)** | step shown level | — | ⌥⌘↑ / ⌥⌘↓ collide with the order list's ⌥⌘↑↓ when the list is focused: settled ⌃⌥⌘↑ / ⌃⌥⌘↓; Use as Working Text none; Compare Levels none |

The three chords the manager asked about: ⌘J Join collided with Finder's Show View Options and the editors' Jump to Selection, so Join is ⌥⌘J (ruled above); Split ⌥⌘S collides with no system or Finder chord (⌘S Save and ⇧⌘S Save As are untouched; ⌥⌘S is unassigned in Finder, Safari, Mail and TextEdit); Run the Recipe on This Item ⌥⌘R collides with no system or Finder chord (Safari alone uses ⌥⌘R for Reload From Origin, an app chord, not a system one), and the three do not collide with each other or with any chord in the inventory above. Every CHANGE above is one build step (section 5), one test case in `MenuShortcutUniquenessTests` and one line in the manual's shortcuts table.

### 5. Build order (small steps; Stage 2 below)

2.1 the command table as a Swift value every menu and context menu renders from, with the test that a surface's context menu equals the table's rows for it (no items move yet); 2.2 the moves: Page › Segments → Edit › Segments ▸ (with Step 1.2 of the segment editor), Canvas Jump → Go, page Group/Ungroup renamed Group as Stack; 2.3 the chord changes of section 4 in one commit with the uniqueness test extended (Import chords off, ⌥⌘I Inspector, Rotate arrows, Back/Forward brackets, Duplicate Window and Find the Documents and Workflow Bar and Run Workflow lose theirs, ⌥⇧⌘R Run Again, the Segments and Levels chords as settled); 2.4 toolbars: one home per tool, the Source pane image controls removed (#6436), the two Edit Segments toggles removed (segment editor Step 1.7); 2.5 wording and icons pass over the table.

## Build order

Written 2026-11-08 for the owner's finding #6411; the rest of this spec's behaviours are not yet cut into steps (the spec is DRAFT for the guard).

### Stage 1 — Run the recipe on the selection

#### Step 1.1 — Run the Recipe on This Item: every row kind, the clicked selection as the scope, a shortcut and a disabled reason (#6411, #4552)
- Behaviours: `menus.project.run-recipe-on-this-item`, `menus.project.run-recipe-shortcut`
- Tests: fichero/Tests/Unit/general/App/MenuTerminologyBoundaryTests.swift, fichero/Tests/Unit/general/App/PageMenuTests.swift, fichero/Tests/Unit/general/Views/Shell/MenuShortcutUniquenessTests.swift, fichero/Tests/Unit/general/Models/RecipeSetupStoreTests.swift, test_start_scope_is_the_selection_6411.py (not yet written), RunRecipeScopeLabelTests.swift (not yet written)
- Size: M

Engine first: the Start plan's scope takes the ids of a selection and resolves them to pages (folder and group as today, a PDF to its pages, a page to itself), refusing an empty scope in words; one test. Then Swift, all on the existing component: `RecipeFolderScope` answers a set of ids and a kind for the clicked row of any kind and for the window's selection; the item's label from the kind and count; the three context menus and the Preview's folder views render it for every row; the Project menu item carries the shortcut and the reason. Reuses `RunRecipeOnFolderMenuItem`, `FocusedRunRecipeOnFolderButton`, `RecipeSetupStore.loadStartPlan`/`start`; no new route.

- test (to write): `test_start_scope_is_the_selection_6411.py` in fichero-server/tests/unit/recipes/ (a PDF resolves to its pages and no other; a page to itself; three ids to their union; an empty scope refuses in words; a landed pass inside the scope is reused)
- test (to write): `RunRecipeScopeLabelTests.swift` in fichero/Tests/Unit/general/App/ (the scope for a click inside and outside the selection, per kind; the label per kind and count; the disabled reason per state; the shortcut declared once)

### Stage 2 — The 2026-11-08 menus review (#6435)

#### Step 2.1 — the command table as one value every menu renders from, and its test (#6435)
- Behaviours: `menus.one-command-table`, `menus.context-menus-mirror-the-table`
- Tests: fichero/Tests/Unit/general/App/MenuTerminologyBoundaryTests.swift, fichero/Tests/Unit/general/App/PageMenuTests.swift, MenuTableTests.swift (not yet written)
- Size: M

Swift only: the table of section 2 as a value; the menu bar and each surface's context menu render their rows from it (the item-verb components exist; hand-rolled items fold in); the equality test per surface. No item moves yet.

- test (to write): `MenuTableTests.swift` in fichero/Tests/Unit/general/App/ (per surface, the rendered titles equal the table's rows; every row has one group; chords unique)

#### Step 2.2 — the moves: Page › Segments to Edit › Segments ▸, Canvas Jump to Go, Group as Stack named (#6435, #6413)
- Behaviours: `menus.edit.segments-submenu`
- Tests: fichero/Tests/Unit/general/App/PageMenuTests.swift, fichero/Tests/Unit/general/Views/Shell/MenuShortcutUniquenessTests.swift, MenuTableTests.swift (not yet written)
- Depends on: 2.1
- Size: S

With `source/segment-editor-crud.md` Step 1.2; the Canvas menu's Jump Back/Forward become Go › Back/Forward on the one history (`source.editor.select-takes-you-there-and-back`); the page Group/Ungroup renamed Group as Stack / Ungroup Stack.

#### Step 2.3 — the chord changes of the audit, in one commit, with the standard-chord table in the uniqueness test (#6435)
- Behaviours: `menus.chords-are-standard-mac`, `menus.shortcut-uniqueness`
- Tests: fichero/Tests/Unit/general/Views/Shell/MenuShortcutUniquenessTests.swift, fichero/Tests/Unit/general/App/MenuShortcutBoundaryTests.swift
- Depends on: 2.1
- Size: M

Section 4's CHANGE rows: Import loses its chords; Inspector ⌥⌘I; Join ⌥⌘J; Rotate ⌥⌘← / ⌥⌘→; Back/Forward ⌘[ ⌘]; Duplicate Window, Find the Documents, Workflow Bar and Run Workflow lose theirs; the settled Segments and Levels chords; the two VERIFY rows resolved; the manual's shortcuts table updated in the same commit.

#### Step 2.4 — toolbars: one home per tool, the leaked bars removed (#6435, #6436)
- Behaviours: `menus.toolbars-one-home-per-tool`
- Tests: fichero/Tests/Unit/general/Views/Shell/MenuShortcutUniquenessTests.swift, ToolbarHomesTests.swift (not yet written)
- Depends on: 2.1
- Size: S

The tool-to-bar table; the Source pane image controls go (Enhance lives in the Edit pane, `source/image-preparation.md` Step 1.6); the Edit Segments toggles go with the segment editor's Step 1.7.

- test (to write): `ToolbarHomesTests.swift` in fichero/Tests/Unit/general/Views/Shell/ (each tool in exactly one bar; no selection verb in a bar)

#### Step 2.5 — wording and icons pass over the table (#6435)
- Behaviours: `menus.wording-and-icons-one-rule`, `menus.less-text-more-indicator`
- Tests: MenuTableTests.swift (not yet written), fichero/Tests/Unit/general/App/MenuTerminologyBoundaryTests.swift
- Depends on: 2.2, 2.3, 2.4
- Size: S

Imperative verbs, the object named when it is not the selection, an ellipsis before a sheet, one icon per command everywhere; the table is the source and the test reads it.

## Open questions (still open)

0. **Per-view filters + metadata in menus?** Each view mode (library layouts, KG, canvas, reader…)
   has its own filters and metadata controls. Should those get menu homes too — e.g. View ▸ Filter ▸
   … per active view — or stay in-surface (toolbar/inspector)? (CD: "maybe they're in menus too, not
   sure.") Decide alongside the submenu structure.
1. **Sort's home** — View ▸ Sort submenu, or nearer the data (the toolbar sort control is the primary
   already)? Where should the *menu* copy live?
2. **Answered** (design lead 2026-10-04, applying the spec's lean): The worst offenders first (create, delete, export) and the long tail later. **How far to unify contextual menus now?** Reuse the existing components everywhere is the end
   state; is a full migration in scope, or convert the worst offenders (creation verbs, delete,
   export) first and leave the long tail?
3. **Answered** (design lead 2026-10-04, applying the spec's lean): Shared components, with the pane as the run context. **Reader/Image verbs** — keep them context-published from the active pane (current pattern) and
   *mirror* into the bar, or centralize as shared components with the pane as run-context?

---

## Ponytail review (2026-09-15) — critical pass, reject the new system

**What the first draft got wrong.** It proposed a new `AppCommand` catalog value type. That is a
NEW SYSTEM sitting beside one that already works — exactly the second-system smell the workspace
spec is busy deleting. Rejected. The app already mandates `@FocusedValue`-routed commands
(swiftui-principles.md), already ships reusable `Focused*Button` / `*MenuItems` components, and
already shares one (`ReaderExportMenuItems`) across the menu bar and a context menu. The "catalog"
exists; it just isn't used everywhere.

**The lazy (correct) plan is subtractive, not additive:**
- The real bug is duplication (`AddItemMenu` hand-rolls verbs the Data menu renders as components).
  Fix = point the duplicating surfaces at the existing components and DELETE the hand-rolled
  `Button`s. Net lines: negative.
- Re-homing (Sort, Workspaces out of the View junk drawer) is moving existing `Section` structs to
  a different `CommandMenu`, not new code.
- The guardrails already exist (`MenuShortcutBoundaryTests`, `MenuTerminologyBoundaryTests`,
  `SidebarContextMenuPolicyTests`); we EXTEND them. No new test framework.
- Cross-platform falls out for free: shared components render in a `CommandMenu` (Mac/iPad) or a
  `.contextMenu`/toolbar `Menu` (iPhone) unchanged. Don't fork verbs per platform.

**What NOT to do (YAGNI):** no `AppCommand`/`CommandRegistry` type; no per-command id enum; no
migration framework; no five-level submenu nesting to "organize" — the fix for a junk drawer is
fewer, better top-level homes, kept shallow. Leave SwiftUI/AppKit standard groups (text editing,
standard Edit items) alone.

**Risks that remain (real):**
- Some verbs still lack a reusable component and are inline today. Extract them ONE at a time in the
  existing `Focused…Button` mold as each surface is deduped — don't big-bang a "make all components"
  pass.
- Re-homing changes muscle memory and shortcuts; keep every existing key equivalent working (the
  `MenuShortcutBoundaryTests` invariants are the safety net) and move menus, not shortcuts.
- iOS/iPad is a real target (release 1, ruled 2026-10-17): the design stays platform-agnostic; iOS-only tests are allowed.

**Verdict:** reject the catalog; adopt "reuse the existing `@FocusedValue` components + HIG
re-homing," landed as small subtractive increments (Data/"+" dedupe first — the clearest win), each
built and pinned by an EXTENDED existing test. Ready for the CD's review; not yet code.

## Future (ideas, not scheduled)
- (#1872) Edit toggle, overflow menu and up/down result navigation in toolbars (Apple Passwords style)
- (#3289) On-device FoundationModels client reusing the fm-bridge JSON contract and Vision OCR at capture on iOS; MLX deferred; later iOS work.
- (#1926) Multiplatform universal app umbrella (iPhone/iPad/Mac one codebase); iOS target exists, remaining work tracked by iPad parity behaviours, so the epic is a vision umbrella.
- (#3327) Localize the interface into Spanish, French, Portuguese via String Catalog; no .xcstrings exists, a later requirement.
- (#3672) iPad/iPhone device-tested interaction feel (momentum, rubber-banding, etc.); needs a TestFlight build and Daniel on a device, not current Mac work.

## Triaged from the backlog (2026-10-04)
- `commands.copy-cut-paste-everywhere` — **[GAP]** (#4257) Copy, cut and paste work on whatever is focused with the richest pasteboard types.
- `commands.smart-paste` — **[GAP]** (#4258) Paste inspects the pasteboard: file URL imports, web URL offers capture, image data creates an image node.
- `commands.every-control-has-help` — **[GAP]** (#4163) every toolbar item, button and icon control carries a .help tooltip, enforced by a guard script so new controls cannot ship without one.
- `commands.pane-focus-navigation` — **[GAP]** (#3686, #4165) focus moves between sidebar, library, Preview, Reader and Inspector by keyboard, and every feature has a documented, conflict-free shortcut.
- `menus.shortcuts-complete-and-discoverable` — **[GAP]** (#3687) every navigation and common action has a menu-bar key equivalent so shortcuts are discoverable from the menus, with no conflicts.
- `menus.toolbar.markup-item-no-chevron-icon-and-text-default` — **[GAP]** (#5275) the markup toolbar item is one icon with no down chevron (tools stay on click, long-press and the menu bar) and a fresh launch with no saved preference shows toolbar items as icon and text.
- `menus.library-view-submenu-named-like-finder` — **[GAP]** (#5002) the Library's view style (as Icons ... as Space) is named and placed like Finder's (a 'Library View' submenu) so it is not mistaken for Workspaces.
- `menus.toolbar.edited-only-by-the-system-editor` **[GAP]** (#5017): toolbar buttons are chosen only with the system's Customize Toolbar; the Workspaces menu has no Toolbar Buttons submenu and the app keeps no second record of which buttons show.
- `menus.toolbar.every-item-named-for-itself` **[BROKEN]** (#5225): with labels showing, every main-toolbar item has its own fixed, descriptive name ('Workflows', 'Markup', 'Default Model') at the standard system width, never a toggle's state such as 'Hide Workflows' used as the group's name; the state goes in the tooltip. Search is one standard system search field with its options in the magnifier's own menu, as in Mail and Finder.
