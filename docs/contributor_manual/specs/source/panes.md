# Source Model — Panes: what each pane shows for what is selected — Design Spec (#6484, #6482, #6483, #6476)

> Milestone: panes
> Manual: TBD — a "What each pane shows" section for Part I (Getting Started): the five panes, the per-pane choice for a selected folder, which pane has the keyboard, and that the app reopens where it was.
>
> Design-led (Testing Constitution). The creative director owns this intent; tests enforce it; code makes them pass.
> **Status: DRAFT — written 2026-11-10 by the spec writer from the owner's UX-window findings (#6484, #6482, #6483, #6476); the owner has answered the open questions (Rulings, below); the manager reads the steps before approval.**
> The pane SYSTEM (composition, splits, workspaces, pane heads, linking) is `ui/panes-workspaces.md`; the selection-kind × surface matrix for non-document nodes (workflow, run, schedule, chat) is `ui/modes-to-panes.md` (`PaneContentPlan`). This spec does not change either: it adds the one thing neither has, a per-pane CHOICE of what a selection shows, and the three findings beside it. `source.editor.focused-pane-is-plain` moved here from `segment-editor-crud.md` as `source.panes.focused-pane-is-plain`.
> Tags are the pipeline's: [OK] built · [PARTIAL] built in part, or built and not seen in a window · [GAP] not built · [BROKEN] built and wrong.

## Intent

A person clicks a folder and sees it ONCE: the Items pane lists it, and the other panes show nothing until asked. Each pane keeps its own small choice of what a selected thing shows (nothing, the thing, a reader of all its content, or a view of it), remembered for that pane, so two Readers side by side can disagree. One pane plainly has the keyboard. Quitting and relaunching reopens the same library at the same document, folder and tab.

## Model

**Panes.** The window's panes are `PaneKind` (`fichero/fichero/Models/PaneList.swift:41`): `library` (Items), `preview` (Source), `reading` (Reader), `segments`, `inspector`, `chat`; the sidebar (Projects) is not a pane leaf. A pane instance is a leaf of the window's `PaneNode` tree with a `UUID` (`\.paneLeafId`, `Views/Shell/ContentView/Layout/PaneSpec.swift:105`); the tree is saved with the window (`WorkspaceLayoutDefaults.rememberPaneList`), so a leaf id survives a relaunch.

**Selection kinds.** What the window's selection IS, one of: `nothing`, `folder`, `page` (one leaf document: an image, a PDF page), `pages` (several leaves), `segment` (one or more segments of a page, `WindowState.focusedRegionSelection`), `rendition` (the Edited image of a page, `source/image-preparation.md`), `artifact` (a reading or result chosen in the Inspector's Artifacts list, the Reader's `artifactLens`), `node` (a workflow, run, schedule, chat: `PaneContentPlan.plan(for:)` already decides these, untouched here).

**Content choices.** What a pane shows for a selection, one of: `nothing` (the pane draws its empty state, `panes.empty-state.blank`, and loads nothing), `theItem` (the selected thing itself: a folder's rows, a page's image, a segment's box), `reader` (a Reader of all the selection's content: every page of a folder in archival order, the page's text, the segment's line), `view(name)` (a view the pane offers for that kind: a folder's canvas, table or map in the Source pane; Lines or Disagreement in the Reader).

**The table.** A pure value, `PaneShowing` (to be written, a new file in the app's Models folder): `PaneShowing.content(pane: PaneKind, selection: SelectionKind, chosen: Choice?) -> Choice` returns the chosen value when the pane offers it for that kind, else the default; `PaneShowing.choices(pane:selection:)` lists what the pane's menu offers (empty = no menu entry, the pane has one sensible content). Defaults (proposed; Ruling 1):

| selection | Items | Source | Reader | Segments | Inspector |
|---|---|---|---|---|---|
| nothing | the project's root | nothing | nothing | nothing | nothing |
| folder | the folder (its rows) | **nothing** · the folder (canvas, table, …) · reader | **nothing** · the folder (its pages, a list) · reader | nothing | the folder |
| page | the page's row in its folder | the page | reader · lines · disagreement (the Reader's lenses, as today) | the page's segments | the page |
| pages | their rows | the first page (as today) | reader of all (`MultiSelectionReaderView`, as today) | nothing | N pages |
| segment | unchanged | the page, the box selected | reader, the line selected | the list, the row selected | the segment |
| rendition | unchanged | the rendition | unchanged | unchanged | the rendition |
| artifact | unchanged | the page | the artifact's reading (`artifactLens`) | unchanged | the artifact |
| node | as `PaneContentPlan` | as `PaneContentPlan` | as `PaneContentPlan` | nothing | as `PaneContentPlan` |

Bold = the owner's ruling (#6484). Every other default is what is built today; the table only names it so a test can hold it. "Unchanged" means the pane keeps showing what the selection's page gave it: a segment, rendition or artifact is chosen INSIDE a page and never empties a pane.

**Where the choice is kept.** Per pane, not per window: `PaneStorage` (`Views/Shell/PaneScopedOption.swift`, #5280) keyed by the leaf id, one key per selection kind that offers a choice (`panes.showing.folder.byPane`, …), the declared default passed as `paneOnly` (#5504) so a NEW pane starts at the default, not at the last choice made anywhere (Ruling 3). A pane with no id (the compact iOS column) reads the shared value. The choice is app-wide across libraries; the PLACE (which document, folder, tab) is per library (the Relaunch section).

## Behaviors

- `source.panes.a-folder-is-not-listed-twice` — **[BROKEN]** (#6484; owner 2026-11-10: clicking a folder shows two table views. Code: the Items pane lists the folder's rows (`LibraryView`); the Reader gets `.surface(.documentReader)` for every `.library` selection (`PaneSurface.swift:125` `stablePanePlan`) and, with a folder as its document, renders the folder's transcript surface, which lists its pages (`ReadingPaneView+Tabs.swift:134-151` `surfaceView(tab: .transcript)`); the Source pane draws the folder as a table then its last view (`FolderContentsPreview`, `library.preview.folder-opens-as-table-then-last-view`, #6172)) with a folder selected and no choice made, the Items pane lists the folder and the Source, Reader and Segments panes show nothing: one list of the folder's pages in the window, not two. *Test:* `PaneShowingTests.swift` (not yet written): `content(.reading, .folder, nil) == .nothing`, `content(.preview, .folder, nil) == .nothing`, `content(.library, .folder, nil) == .theItem`.
- `source.panes.choice-table-is-a-pure-value` — **[GAP]** (#6484) `PaneShowing` is a value with no view, store or environment in it: `content(pane:selection:chosen:)` is total (every pane × every kind answers), a `chosen` the pane does not offer for that kind falls to the default rather than being honoured, and `choices(pane:selection:)` is empty wherever only one content makes sense (Items for anything; Inspector for anything; Segments for a folder). The window's panes read the table and nothing else decides what a selection shows, so `PaneContentPlanTests`' "every mode decides all four panes" holds for every selection kind too. *Test:* `PaneShowingTests.swift` (not yet written): the table is total; an unoffered choice falls to the default; the existing PaneContentPlanTests (exists, listed in the step) for the node row.
- `source.panes.nothing-costs-nothing` — **[GAP]** (#6484; the owner's "quickest") a pane whose content for the selection is `nothing` makes no engine call: no children load, no transcript fetch, no segment list, no thumbnail, and it draws `PaneEmptyStateView` (`panes.empty-state.blank`). Selecting a folder with every pane at the default costs the Items pane's one `loadChildren` and nothing else. *Test:* `PaneShowingLoadsNothingTests.swift` (not yet written): a Reader and a Source pane hosted with a folder selection and `nothing` chosen record zero store calls (the `DocumentStore` test double counts them).
- `source.panes.each-pane-chooses-what-a-selection-shows` — **[GAP]** (#6484) the pane menu (`panes.chrome.one-pane-menu`'s + on the head and right-click on the head; until that lands, the head's existing kind menu) carries one submenu per selection kind the pane offers a choice for, named by the kind: "When a folder is selected ▸ Nothing · The folder · Reader of its contents · Canvas …", "When a page is selected ▸ …". The entries are `PaneShowing.choices(pane:selection:)`; a pane with no choice for a kind shows no submenu for it. Choosing applies at once to the current selection. *Test:* `PaneShowingMenuTests.swift` (not yet written): the submenu's entries equal `choices(...)`; a pane with an empty `choices` has no submenu; the existing PaneMenuEntriesShapeTests (exists, listed in the step) gains the submenu's place in the menu order.
- `source.panes.choice-is-remembered-per-pane` — **[GAP]** (#6484; owner 2026-11-10: per pane, not for the window) two panes of one kind keep different choices (a Reader beside a Reader: one shows the folder's contents, one nothing); the choice is keyed by the pane's leaf id through `PaneStorage`, survives a relaunch with the pane list, and is not disturbed by splitting, closing or kind-switching a sibling (`panes.instance-safe`). A new pane starts at the default (Ruling 3). *Test:* PaneScopedOptionTests (exists, listed in the step) (the map rules, exists) and `PaneShowingTests.swift` (not yet written): two leaf ids, two values; a third id reads the `paneOnly` default.
- `source.panes.make-a-choice-the-default` — **[GAP]** (#6484; owner 2026-11-10: a way to make a choice the default) the pane menu's submenu carries "Make this the default" beside the choices: it stores the pane's current choice for that selection kind as the app-wide default, which every NEW pane starts from and every pane without its own choice reads; it changes no pane that already has a choice. Until it is used the default is the table's. *Test:* `PaneShowingMenuTests.swift` (not yet written): after "Make this the default" a new leaf id reads the new value; an existing leaf with its own choice keeps it.
- `source.panes.a-choice-for-one-item` — **[GAP]** (#6484; owner 2026-11-10: a way to make it special for a certain page or folder) a pane can keep a choice for one particular item (a folder now; a page when its kind offers a choice): "Always show this folder as ▸ …" stores it by the item's id, and it wins over the pane's choice and the default while that item is selected; "Forget this" removes it. It is per pane like the choice, and a deleted item's entry is dropped when the library next loads. *Test:* `PaneShowingTests.swift` (not yet written): `content` with an item override returns it; without one falls to the pane's choice, then the default.
- `source.panes.same-rule-for-every-selection-kind` — **[GAP]** (#6484; owner 2026-11-10: the same idea for a page, a segment, a rendition, an artifact) the table has a row for every selection kind and the Model table's defaults are the built behaviour, so adding a choice for a kind is a row change, never a new code path: a segment, rendition or artifact never empties a pane that was showing its page (`unchanged`), and the Reader's lenses (Content, Lines, Disagreement) are the `view(...)` choices of its page row, not a second mechanism. *Test:* `PaneShowingTests.swift` (not yet written): every `SelectionKind` case has a default per pane; `content(_, .segment, nil)` equals `content(_, .page, nil)` for Items and Reader (unchanged).
- `source.panes.focused-pane-is-plain` — **[GAP]** (#6476; owner 2026-11-10: it is hard to know the focused view, so hard to know where keyboard input goes; moved here from `segment-editor-crud.md` Step 1.25. Code: `PaneFocus` (`ContentView.swift:16`, `@FocusState focusedPane` + `paneFocusHint`, `ContentView.swift:798-805`), `cyclePaneFocus` left to right (`ContentView+ActionsNavigation.swift:52`), only the Items pane reads `isPaneFocused` (`ContentView+Navigation.swift:74`), and `LibrarySelectionStrengthTests` pins the selection fill as the shared GREY in both focus states (ruled 2026-10-11)) exactly one pane reads as focused at any time: its head carries an accent underline and its selection fills in the accent colour, while the other panes' selections fill grey; the window's key target (the Items list, the Source, the Reader, an Order list, the Inspector) is the one drawn so, and it changes with a click, Tab / Shift-Tab (`cyclePaneFocus`) or ⌘-arrow. The owner's accent fill supersedes the 2026-10-11 grey-in-both-states pin (Ruling 4). *Test:* the focused-pane identity and its style are a pure value, `FocusedPaneStyleTests.swift` (not yet written: `FocusedPaneStyle(focused: PaneFocus?, pane: PaneFocus) -> (underline: Bool, fill: .accent | .grey)`, exactly one pane underlined for any focus, none when focus is nil); the existing PaneFocusKindTests (exists, listed in the step); LibrarySelectionStrengthTests (exists, listed in the step) changes to the accent/grey split. The drawing: not run.
- `source.panes.every-pane-claims-focus-on-click` — **[PARTIAL]** (#6476; built: the sidebar (`.focused`), Items (`onRequestFocus`), the Segments pane (#4942); not built: the Reader, the Source and the Inspector write `paneFocusHint` only through their own handlers, and `PaneFocus.content` "names no view" (#5824) so FocusState never lands there) a click anywhere in a pane, including its head and its empty area, makes it the focused pane; a pane that cannot take key input (nothing in it) still takes the underline so the person sees where the next key would go. *Test:* `FocusedPaneStyleTests.swift` (not yet written): a hint set by each kind's click resolves to that kind; the existing LaunchPaneFocusTests (exists, listed in the step) (the window opens on the sidebar).
- `source.panes.relaunch-returns-to-the-same-place` — **[BROKEN]** (#6483; owner 2026-11-10: a relaunch restores `viewMode=library, selectedItem=nil`, then a document id from ANOTHER library (`52a7edca…`), `loadChildren 404 … falling back to the root set` (`DocumentStore.swift:510`, the #6479 fallback). Code: the place is three `@SceneStorage` keys per WINDOW (`viewModeType`, `viewModeItemId`, `selectedSidebarItem`, `LibraryWindow.swift:96-98`, mirrored by `ContentView+Persistence.swift:259`), none keyed by library; `assignLibrary` (`LibraryWindow+Actions.swift`) rewrites `libraryWindow.libraryId` and leaves the three alone, so a window that switched library carries the old library's id into the new one) the place a library was left at is kept PER LIBRARY: `LibraryPlace(libraryId → viewModeType, viewModeItemId, selectedSidebarItem, browserSelection, inspectorTab)` written on every change (`UserDefaults`, one record per library; the scene keeps only `libraryWindow.libraryId`), and read when a window opens or switches to that library. An id the library no longer has restores the nearest ancestor it still has, else the Sources folder (`OpeningSelection.sourcesFolder`), and logs which. Done looks like: quit and relaunch (and Stop/Run from Xcode) opens the same document, folder and tab. *Test:* `RelaunchPlaceTests.swift` (not yet written): a place written for library A is not read for library B; a stale id resolves to its ancestor, then the Sources folder; the existing ContentViewPersistenceTests (exists, listed in the step) (the type/id mapping) and SceneStorageUsageTests (exists, listed in the step).
- `source.panes.place-is-written-when-it-changes` — **[PARTIAL]** (#6483, the owner's second suspect: state not flushed when Xcode stops the process; `@SceneStorage` is written by the system at its own time, which a SIGKILL never reaches) the place is written when the selection changes, not at quit, so a Stop in Xcode, a crash or a force-quit lose at most the last change in flight. Built: the `@SceneStorage` mirror writes on change (`ContentView+Persistence.swift:259`); the system's flush is what is late. *Test:* `RelaunchPlaceTests.swift` (not yet written): `LibraryPlace.write` is called from the selection change, not from a scene-phase hook; seen in a window: not run.
- `source.panes.what-is-restored` — **[PARTIAL]** (#6483) the restored set is named in one place and nothing else restores: per library, the place (above); per window, the pane list and splits (`WorkspaceLayoutDefaults`), column visibility and sidebar width; per pane, the choices of this spec and the options of `panes.options-per-pane`; per window and surface, the Inspector tab (`inspectorSelectedTab`), the Reader lens and notes mode, the Chat tab. A thing not in the list (zoom, scroll position, the magnifier) is not promised. Built: every item but the per-library place. *Test:* `RelaunchPlaceTests.swift` (not yet written) lists the keys; SceneStorageUsageTests (exists, listed in the step), WorkspaceLayoutDefaultsTests (exists, listed in the step).
- `source.panes.compact-width-shows-one-pane` — **[PARTIAL]** (#6484; built by `m2p.ios.sidebar-to-library` #5964 and `CompactShellPolicy` (`ShellLayoutPolicy.swift:163`): the compact column shows Projects, then Items, then the Reader pushed for a leaf (`resolveCompactReaderLeaf`, never a folder), the Inspector as a sheet (`InspectorPlacement.sheet`)) at compact width (iPhone, a narrow iPad window) the table still decides what each pane shows; the difference is that one pane is on screen at a time: a folder with Items at `theItem` drills in place; a pane whose content is `nothing` is never pushed (the Reader does not open on a folder), and a pane whose content is `theItem` or `reader` is the push or the sheet. No pane leaf ids exist at compact width (`shouldUseSplittablePane` is false), so the choice read is the SHARED value per kind (`PaneStorage` with a nil pane), set from the same submenu in the column's toolbar menu. *Test:* `PaneShowingCompactTests.swift` (not yet written): with `nothing` chosen the push route for a folder is `.none`; the existing CompactShellPolicyTests (exists, listed in the step) and CompactReaderLeafTests (exists, listed in the step).
- `source.panes.regular-width-is-the-mac-table` — **[GAP]** (#6484) at regular width (iPad, Mac) the split panes read the same table, the same per-pane keys and the same menu as the Mac; nothing in `PaneShowing` branches on platform. *Test:* `PaneShowingTests.swift` (not yet written) builds on every platform with no `#if`; the existing AdaptiveShellPolicyTests (exists, listed in the step).
- `source.panes.touch-focus-is-the-last-tap` — **[GAP]** (#6476; iOS) on touch there is no hover and no Tab: the focused pane is the pane last tapped (or, at compact width, the one on screen), drawn the same way (underline, accent fill); an iPad with a keyboard cycles with Tab as the Mac does. *Test:* `FocusedPaneStyleTests.swift` (not yet written): the style function has no platform branch; at compact width the visible column is the focused pane.

## Build order

Written 2026-11-10 for #6484, #6476 and #6483. For one lane, in order. 1.1 before anything; 1.4 and 1.5 are independent of 1.2 and 1.3 and may land first if the owner wants the relaunch fix early.

### Stage 1 — one list, one choice per pane, one focused pane, the same place on relaunch

#### Step 1.1 — the choice table as a pure value; a folder shows nothing by default (#6484)
- Behaviours: `source.panes.choice-table-is-a-pure-value`, `source.panes.a-folder-is-not-listed-twice`, `source.panes.nothing-costs-nothing`
- Tests: PaneShowingTests.swift (not yet written), PaneShowingLoadsNothingTests.swift (not yet written), fichero/Tests/Unit/general/Views/Shell/PaneContentPlanTests.swift
- Size: S

Swift only. Red test first: on base, the Reader with a folder selected renders the transcript surface. Write `PaneShowing` with the Model table; the Reader, Source and Segments hosts ask it before mounting a surface and draw `PaneEmptyStateView` for `nothing`; the node row delegates to `PaneContentPlan` unchanged.

- test (to write): `PaneShowingTests.swift` in fichero/Tests/Unit/general/Views/Shell/ (the table is total; folder defaults; an unoffered choice falls to the default)
- test (to write): `PaneShowingLoadsNothingTests.swift` in fichero/Tests/Unit/general/Views/Shell/ (a pane at `nothing` makes no store call for a folder selection)

#### Step 1.2 — the per-pane choice in the pane menu, remembered per pane (#6484)
- Behaviours: `source.panes.each-pane-chooses-what-a-selection-shows`, `source.panes.choice-is-remembered-per-pane`
- Tests: PaneShowingMenuTests.swift (not yet written), fichero/Tests/Unit/general/Views/Shell/PaneScopedOptionTests.swift, fichero/Tests/Unit/general/Views/Shell/PaneMenuEntriesShapeTests.swift
- Depends on: 1.1
- Size: M

One `PaneStorage` key per selection kind, `paneOnly` default; the submenu is rendered from `choices(...)` by the head's menu and, when `panes.chrome.one-pane-menu` lands, by that menu with no second list.

- test (to write): `PaneShowingMenuTests.swift` in fichero/Tests/Unit/general/Views/Shell/ (entries equal `choices`; no submenu when empty; two panes keep two values across a save and load of the pane list)

#### Step 1.3 — every selection kind in the table (#6484)
- Behaviours: `source.panes.same-rule-for-every-selection-kind`
- Tests: PaneShowingTests.swift (not yet written)
- Depends on: 1.1
- Size: S

Rows for page, pages, segment, rendition, artifact with today's behaviour as the default; the Reader's lenses become its page row's `view(...)` choices. No new menu entries unless the owner names one (Ruling 2).

#### Step 1.4 — one pane reads as focused (#6476)
- Behaviours: `source.panes.focused-pane-is-plain`, `source.panes.every-pane-claims-focus-on-click`
- Tests: FocusedPaneStyleTests.swift (not yet written), fichero/Tests/Unit/general/Views/Shell/PaneFocusKindTests.swift, fichero/Tests/Unit/general/Views/Library/LibrarySelectionStrengthTests.swift, fichero/Tests/Unit/general/App/LaunchPaneFocusTests.swift
- Size: M

`FocusedPaneStyle` pure; every pane host reads it for its head underline and passes the fill to its list; every pane writes `paneFocusHint` on click, head included. `LibrarySelectionStrengthTests` changes with the ruling (Ruling 4). Seen in a window: the manager, on the Pro.

- test (to write): `FocusedPaneStyleTests.swift` in fichero/Tests/Unit/general/Views/Shell/ (exactly one underline; accent fill only on the focused pane; nil focus underlines none; no platform branch)

#### Step 1.5 — relaunch returns to the same place, per library (#6483)
- Behaviours: `source.panes.relaunch-returns-to-the-same-place`, `source.panes.place-is-written-when-it-changes`, `source.panes.what-is-restored`
- Tests: RelaunchPlaceTests.swift (not yet written), fichero/Tests/Unit/general/Views/Shell/ContentViewPersistenceTests.swift, fichero/Tests/Unit/general/Views/Shell/SceneStorageUsageTests.swift, fichero/Tests/Unit/general/Views/Shell/WorkspaceLayoutDefaultsTests.swift
- Size: M

Red test first: a place written while library A is open is read after a switch to library B. `LibraryPlace` record per library; `restorePersistedState` reads it for the window's library; `assignLibrary` writes the old library's place before switching and reads the new one; the stale-id rule resolves to the ancestor, then Sources, and logs which. Ruling 5 decides whether `@SceneStorage` keeps the three keys as a mirror or loses them.

- test (to write): `RelaunchPlaceTests.swift` in fichero/Tests/Unit/general/Views/Shell/ (per-library isolation; stale id → ancestor → Sources; written on change; the restored-set list)

#### Step 1.6 — compact and regular width (#6484)
- Behaviours: `source.panes.compact-width-shows-one-pane`, `source.panes.regular-width-is-the-mac-table`, `source.panes.touch-focus-is-the-last-tap`
- Tests: PaneShowingCompactTests.swift (not yet written), fichero/Tests/Unit/general/Views/Shell/CompactShellPolicyTests.swift, fichero/Tests/Unit/general/Views/Shell/CompactReaderLeafTests.swift, fichero/Tests/Unit/general/Views/Shell/AdaptiveShellPolicyTests.swift
- Depends on: 1.2, 1.4
- Size: S

`CompactShellPolicy.route` consults `PaneShowing` before pushing; the shared value is the compact column's choice; the focused pane at compact width is the visible column. Needs an iOS issue (Ruling 6). Seen on a simulator: not run.

- test (to write): `PaneShowingCompactTests.swift` in fichero/Tests/Unit/general/Views/Shell/ (a folder with `nothing` chosen pushes no Reader; a page pushes as today; the shared value is read with a nil pane)

#### Step 1.7 — make a choice the default, or keep one for one folder (#6484)
- Behaviours: `source.panes.make-a-choice-the-default`, `source.panes.a-choice-for-one-item`
- Tests: PaneShowingMenuTests.swift (not yet written), PaneShowingTests.swift (not yet written)
- Depends on: 1.2
- Size: M

The resolution order in `PaneShowing.content` becomes item override, then the pane's choice, then the app-wide default, then the table; each layer is one more optional argument, not a new code path. The two menu entries write the app-wide default and the item map.

- test (to write): `PaneShowingMenuTests.swift` in fichero/Tests/Unit/general/Views/Shell/ (make-default reaches a new pane only; item override wins, forget removes it)

## iOS and iPadOS

The table is the same on every platform; the width decides how many panes are on screen, never what a pane shows. Compact width (iPhone, a narrow iPad window, `horizontalSizeClass == .compact`): one column at a time, `NavigationSplitView` collapsed by the system (`m2p.ios.no-stack-around-split`), Projects → Items → the Reader as a push for a leaf, the Inspector as a sheet; a `nothing` content never pushes; the pane choice is the shared value, set from the column's toolbar menu; focus is the visible column, drawn with the same underline, and no hover is assumed anywhere. Regular width (iPad, Mac): split panes, pane leaf ids, per-pane choices, Tab cycling with a hardware keyboard; touch focus is the last tap.

## Relaunch and restoration (#6483)

What comes back, and at which scope, is the `source.panes.what-is-restored` list; the per-library place is the one thing not yet kept per library and is Step 1.5. Restored order on open: the library (`libraryWindow.libraryId`), then the library's place (view mode and item, sidebar selection, browser selection, Inspector tab), then the window's pane list and the per-pane choices; a stale item id resolves upward, never to a 404 fallback the person has to notice in a log.

## Rulings (owner, 2026-11-10)

1. **The default table.** A selected folder shows nothing in Source, Reader and Segments by default; every other default is today's behaviour. The person can choose what a folder shows from the pane menu; the exact defaults are settled in the UX pass, as table rows, not code.
2. **Which panes offer a choice.** Source and Reader offer every option for a folder (Nothing, The folder, Reader of its contents, the Source's views). A page, segment, rendition or artifact gets a menu entry later, when a case is named; the table already has their rows. Two additions: a person can make a choice the default for that kind (`source.panes.make-a-choice-the-default`), and can give one particular folder its own choice (`source.panes.a-choice-for-one-item`).
3. **A new pane's starting choice.** The default (`paneOnly`), never the last choice made anywhere.
4. **Selection fill.** Accent in the focused pane, grey elsewhere; this replaces the 2026-10-11 grey-in-both-states pin and `LibrarySelectionStrengthTests` changes with it.
5. **Where the place lives.** The per-library record alone, written on change; `@SceneStorage` keeps only the library id.
6. **iOS.** One new issue, "Panes on iOS: the choice table at compact width, touch focus", in the `panes` milestone (#6493).
7. **Milestone.** Create `panes` with #6484, #6483, #6476 and the iOS issue; `panes-workspaces` and `modes-to-panes` stay as they are.
8. **`segment-editor-crud.md` Step 1.25.** The merge of `ux-polish` drops `source.editor.focused-pane-is-plain` from Step 1.25; this branch's one-line header pointer stays.
