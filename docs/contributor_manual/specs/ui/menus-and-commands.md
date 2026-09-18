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
  (`ReadKnowledgeMenuCommands`, wired at `FicheroApp.swift` in the `after: .toolbar` region.)
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
  commands reusing the same key with no text editor focused — File's ⌘T "New Window", Image Preview's
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
> `Knowledge` (`ReadKnowledgeMenuCommands`) replace the former `CommandMenu("Data")`. The remaining
> per-menu item placements below are still the proposal; only the top-level bar and the
> Import/Find/Full-Screen moves (see Changelog) have landed.

Two domain menus (**Read**, **Knowledge**) carry the archival workflow; the rest are the macOS
standards, each cleaned to its true job. Title-case labels; verbs for actions; ellipsis where more
input is needed; toggled items use one changeable label (Show/Hide); icons only where they clarify,
uniform per group.

- **File** — get sources in and out (Parts III, IX). New Library…, Open…, Open Recent ▸, Close
  Library · New Window, Duplicate Window · **Import ▸** (Link/Copy/Move Files…, New Folder) · **Export
  ▸** (Markdown…, Word…, BibTeX…, Markdown Static Site…) · Grant Folder Access… · Print…
- **Edit** — change the selection. Undo/Redo · Cut/Copy/Paste · Delete · Select All · Rename · Find…
  (the app's own search surfaces own ⌘F; keep the routed Select All / Undo from `MenuShortcutBoundaryTests`.)
- **View** — how it LOOKS (Part V, appearance only). As Icons/List/Columns/Gallery (⌘1–6) · **Sort By
  ▸** · **Preview ▸** (Side/Bottom/Hide, Representation) · Show/Hide Sidebar · Show/Hide Inspector
  (⌃⌘I) · Panes ▸ · **Workspaces ▸** (⌘⌥1–5, Save…, Manage…) · Enter Full Screen. (Submenus, per the
  ratified nesting.)
- **Go** — move around. Back/Forward · Enclosing Folder · Reveal in Sidebar · recent locations.
- **Read** — the reading & annotating surface (Parts IV, VI). **Reader Lens ▸** (Content, Translation,
  Artifact…) · **Representation ▸** · **Annotate ▸** (markup tools, ruler) · **Extract ▸** (Run OCR,
  Run NLP, Detect Language) · Zoom (In/Out/Actual Size/Fit) · **Magnifier ▸** (Loupe, panel) · Next/
  Previous Page. Everything you do WHILE reading a source lives here, not scattered in View.
- **Knowledge** — making & querying meaning (Parts VII, VIII; the AI/data workflow). New Claim, New
  Entity · SPARQL Console… (#3298, its own window) · **Workflows ▸** (New Workflow/Chain/Comparison/
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
- `menus.bar-structure` — a source/policy test (the `MenuShortcutBoundaryTests` shape) asserts the
  menu bar declares exactly these top-level menus and that each named command lives in its ruled
  home (e.g. Reader Lens under **Read**, New Workflow under **Knowledge**, Sort under **View ▸ Sort**),
  NOT in a generic dump. Fails if a command drifts back to the wrong menu.
- `menus.submenu-nesting` — asserts View composes its groups as `Menu` submenus (Workspaces/Sort/
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

**Open**: is iOS/iPad a first-class target now, or Mac-first with iPad to follow? The design holds
either way (shared components), but scope of the cross-platform tests depends on the answer.

---

## Behaviors (each → one pinning test, extending the tests that already exist)

- `menus.no-hand-rolled-duplicates` — **[PROPOSED]** a verb that has a reusable component
  (`Focused*Button` / `*MenuItems`) is never re-authored as a raw `Button` on another surface.
  *Test:* extend `MenuTerminologyBoundaryTests` (source guardrail) to fail if e.g. `AddItemMenu`
  contains `Button("New Folder")` while `FocusedNewFolderButton` exists.
- `menus.data-and-plus-agree` — **[PROPOSED]** the menu-bar "Data" menu and the toolbar "+" render
  the same creation verbs from the same components. *Test:* assert both source sites reference the
  identical `Focused*Button` set (source guardrail), the `ReaderExportFocusedValueTests` shape.
- `menus.natural-home` — **[PROPOSED]** appearance/layout only under View; Sort and Workspaces are
  NOT in the View dump. *Test:* a source/policy assertion on which sections `ViewMenuCommands`
  composes (it must not compose `SortSection`/`WorkspaceCommandsSection` once re-homed).
- `menus.shortcut-uniqueness` — **[OK]** (enforced 2026-09-16, dfa937946) no two commands share a key
  equivalent in one scope (the ⌘⌥1→loupe and double-minted ⌘⌥F "Find in Artifact"/"Find in Page"
  defects the workspace consolidation hit). *Enforced:*
  `Tests/Unit/general/Views/Shell/MenuShortcutUniquenessTests.swift` enumerates every ⌘⌥ chord the app
  mints — the workspace slots map to ⌘⌥1–5 in declaration order, all distinct, none is the loupe's
  ⌘⌥L — and a source-scan fails if any ⌘⌥ literal chord is claimed by two commands. Complements the
  older `MenuShortcutBoundaryTests` (single-owner ⌘Z, ⌘I/⌘F non-collision). **Made `#if`-aware
  2026-09-18** (see Changelog): the scan tracks `#if`/`#elseif`/`#else` branch nesting per mint and
  only flags a chord shared across branches that are NOT provably mutually exclusive, so one command
  declared once per platform branch (`#if canImport(AppKit) / #else`) is not a false collision.
- `menus.context-matches-bar` — **[PROPOSED]** a verb in both a context menu and the menu bar is the
  SAME component (same label/icon/shortcut/enablement). *Test:* the `SidebarContextMenuPolicyTests`
  pure-function shape — assert the context menu's verb list is drawn from the shared components.

---

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

## Open questions (still open)

0. **Per-view filters + metadata in menus?** Each view mode (library layouts, KG, canvas, reader…)
   has its own filters and metadata controls. Should those get menu homes too — e.g. View ▸ Filter ▸
   … per active view — or stay in-surface (toolbar/inspector)? (CD: "maybe they're in menus too, not
   sure.") Decide alongside the submenu structure.
1. **Sort's home** — View ▸ Sort submenu, or nearer the data (the toolbar sort control is the primary
   already)? Where should the *menu* copy live?
2. **How far to unify contextual menus now?** Reuse the existing components everywhere is the end
   state; is a full migration in scope, or convert the worst offenders (creation verbs, delete,
   export) first and leave the long tail?
3. **Reader/Image verbs** — keep them context-published from the active pane (current pattern) and
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
- iOS/iPad target scope is unconfirmed (open question) — the design is platform-agnostic, but don't
  write iOS-only tests until it's a real target.

**Verdict:** reject the catalog; adopt "reuse the existing `@FocusedValue` components + HIG
re-homing," landed as small subtractive increments (Data/"+" dedupe first — the clearest win), each
built and pinned by an EXTENDED existing test. Ready for the CD's review; not yet code.
