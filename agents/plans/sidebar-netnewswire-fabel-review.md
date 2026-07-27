# Fabel Review — NetNewsWire's Sidebar → Fichero's Sidebar

**Status:** read-only review. No source edited, no issues filed, no build run.
**Date:** 2026-07-25
**Reference:** `Ranchero-Software/NetNewsWire`, `Mac/MainWindow/Sidebar/` (MIT licence).
**Subject:** `fichero/fichero/Views/Sidebar/` on `integration`.
**Prior art:** `docs/design/sidebar-view-fabel-review.md` (Phase 1). This is Phase 2 and
does not restate it — Phase 1 was an internal audit; this is a comparison against a
mature AppKit sidebar.

NetNewsWire is AppKit/`NSOutlineView`; Fichero is SwiftUI on macOS 26. Every idea below
is translated to its native SwiftUI equivalent. Where there is no equivalent, that is
stated rather than papered over.

**Lane note:** #4058 (workflow nodes not rendering under Default Workflows) is owned by
another worker in its own worktree. Nothing here touches the node-tree build path.

**Licence note:** all proposals below are *ideas and approaches*, not code. Two places
where lifting literal code would be tempting are flagged inline; both would require the
MIT attribution to be carried in the file header.

---

## (a) What NetNewsWire does well

### Visual craft

**A1. One metrics struct owns the entire row rhythm.**
`Cell/SidebarCellAppearance.swift` is a single `Equatable` struct holding
`imageMarginRight = 4.0`, `unreadCountMarginLeft = 10.0`, and a `RowSizeStyle` switch
that yields 16/19/22pt icons against 11/13/15pt text. Every row — feed, folder, smart
feed — reads its geometry from that one value. Change the struct, the whole sidebar
re-rhythms coherently. Nothing in the codebase hardcodes an inset.

**A2. Layout is computed once, in one function, and the badge always wins.**
`Cell/SidebarCellLayout.swift` computes three rects together. Icon and title are both
`centeredVertically(in: bounds)` — the vertical centring is *derived*, not a
hand-tuned padding. And the title is explicitly clipped so the unread count can never
be pushed off:

```swift
let textFieldMaxX = rUnread.minX - appearance.unreadCountMarginLeft
if rTextField.maxX > textFieldMaxX { rTextField.size.width = textFieldMaxX - rTextField.minX }
```

That single clamp is why a feed named *"Very Long Publication Name For Testing"* with
4,812 unread never looks broken.

**A3. The unread count on macOS 26 abandons the pill — and NNW already ships that branch.**
This is the highest-value visual finding in the whole review. `UnreadCountView.swift`:

```swift
static let useTraditionalBadge: Bool = { if #available(macOS 26, *) { return false }; return true }()
static let textSize: CGFloat = { useTraditionalBadge ? 11.0 : 13.0 }()
static let textFont: NSFont = {
    useTraditionalBadge
        ? NSFont.monospacedDigitSystemFont(ofSize: textSize, weight: .semibold)
        : NSFont.monospacedDigitSystemFont(ofSize: textSize, weight: .regular)
}()
```

On macOS 26 the drawn capsule is gone. What remains is 13pt monospaced-digit text at
`.secondaryLabelColor`, going white when the row is selected. Also: zero is *absent*,
not `"0"` (`unreadCount < 1 ? "" : "\(unreadCount.formatted())"`), and the measured
text size is cached (`private static var textSizeCache = [Int: NSSize]()`) so counting
does not cost layout.

The translation is unusually clean: **that treatment is exactly what SwiftUI's native
`.badge()` renders on macOS 26.** Secondary label, monospaced digits, no pill, correct
selection inversion, and it hides itself at zero. Fichero can have NNW's macOS 26 badge
for the price of one modifier.

**A4. Icon tinting is state-driven, not per-call-site.**
`Cell/SidebarCell.swift` has a `backgroundStyle` `didSet` that retints: SF Symbols go
white when the row is selected (`.emphasized`), otherwise
`iconImage.preferredColor ?? NSColor.controlAccentColor`. One hook, applied uniformly.
Every other setter is change-gated before it invalidates layout, so an unchanged value
costs nothing.

**A5. Top-level pseudo-feeds are visually de-indented.**
`SidebarOutlineView.swift` overrides `frameOfCell(atColumn:row:)` and subtracts
`indentationPerLevel` when `parentNode.isRoot && node.representedObject is PseudoFeed`.
Today / All Unread / Starred sit flush left, structurally children but visually
first-class. Small override, large effect on how "settled" the sidebar reads.

**A6. Progress chrome slides away completely when idle.**
`SidebarStatusBarView.swift` animates `bottomConstraint.constant` between `0` and
`-(heightConstraint.constant)` over 0.2s, driven by `.progressInfoDidChange` coalesced
through `CoalescingQueue.standard`. Idle state is not a greyed-out bar — it is *no bar*.

**A7. Group headers get their own cell path.**
`outlineView(_:isGroupItem:)` routes to `configureGroupCell`, a distinct
`NSTableCellView` identifier, never the data cell. Headers cannot accidentally inherit
row affordances.

**A8. Icons are prefetched before first paint.**
`collectExpandedFeeds(in:into:)` → `prefetchFeedIcons()` → `IconImageCache.shared`,
called from `viewDidLoad`, from `rebuildTreeAndReloadDataIfNeeded()`, and again from
`outlineViewItemDidExpand`. Newly visible rows have their icon in hand *before* they
draw. This is precisely Fichero's own "Every Frame Perfect" bar, enforced structurally.

### Structure and selection

**A9. Restoration is one value object, restored as one unit.**
`SidebarWindowState.swift` is an `NSSecureCoding` struct with exactly three fields:
`isReadFiltered`, `expandedContainers`, `selectedFeeds`. It is *computed* on demand
rather than incrementally maintained:

```swift
var windowState: SidebarWindowState {
    let expandedContainers = expandedTable.compactMap { $0.userInfo as? [String: String] }
    let selectedFeeds = selectedFeeds.compactMap { $0.sidebarItemID?.userInfo as? [String: String] }
    return SidebarWindowState(isReadFiltered: isReadFiltered, expandedContainers: expandedContainers, selectedFeeds: selectedFeeds)
}
```

`restoreState(from:)` then applies expansion, filter exceptions, and **one batched**
`selectRowIndexes(_:byExtendingSelection: false)`, then `focus()`, then `isReadFiltered`
— in that order, in one function. There is no reconcile-afterwards step because there is
nothing to reconcile.

**A10. Defaults are applied first, restoration overlays them.**
`viewDidLoad` expands all top-level nodes, with the intent written down in a comment:
`// Expand top level items by default. If there is state to restore, overlay this.`
The default expansion is not conditional on the absence of saved state; saved state
simply wins where it speaks.

**A11. Filter exceptions — filtering never hides what you have selected.**
`addAllSelectedToFilterExceptions()` / `addToFilterExceptionsIfNecessary(_:)` /
`addParentFolderToFilterExceptions(_:)`. When hide-read is on, the selected feed *and
its parent folder* are exempted from the filter. The selection cannot vanish out from
under you, and a selected child cannot be orphaned by a filtered-out parent. Exceptions
are re-seeded on every rebuild and reset immediately after, so they never accumulate.

**A12. Selection can be vetoed before it happens.**
`outlineView(_:selectionIndexesForProposedSelection:)` inspects the *proposed* set and,
if it contains a group item, returns the **current** selection unchanged — deliberately
not a filtered version of the proposal. A shift-drag across a header does not silently
lose rows; it does nothing.

**A13. Tree rebuilds are coalesced, and guarded against reentrancy.**
`CoalescingQueue(name: "Rebuild Tree Queue", interval: 1.0)`, plus
`if !animatingChanges && !BatchUpdate.shared.isPerforming` before any rebuild. A burst
of fourteen notifications produces one rebuild, and never one mid-animation.

**A14. Updates are surgical, never a reload.**
`applyToCellsForRepresentedObject(_:_:)` enumerates only *available* row views, finds
the cells representing one object, and reconfigures those. `faviconDidBecomeAvailable`,
`feedIconDidBecomeAvailable`, `displayNameDidChange`, and `feedSettingDidChange` all
route through it. This is the AppKit expression of Fichero's own "no wholesale list
re-render" rule.

**A15. Two context menus, chosen by where the click landed.**
`contextualMenuForSelectedObjects()` when the right-click is inside the selection;
`contextualMenuForClickedRows()` when it is outside. And `menu(for objects:)` switches
on *count* first — no-selection, multiple, then single — so a 12-row selection gets a
menu built for 12 rows rather than a single-row menu with plural verbs.

### Drag and drop

**A16. Mixed payloads are rejected outright, not silently narrowed.**

```swift
if (draggedFolders == nil && draggedFeeds == nil) || (draggedFolders != nil && draggedFeeds != nil) {
    return dragOperationNone
}
```

**A17. The payload is classified once, then routed by shape.**
`enum DraggedFeedsContentsType { case empty, singleLocal, singleNonLocal, multipleLocal, multipleNonLocal, mixed }`
— one classification, then per-shape validators. No validator re-inspects the payload.

**A18. Illegal drop targets are retargeted, not rejected.**
`ancestorThatCanAcceptLocalFeed(_:)` walks up to the nearest legal container and then
rewrites the drop target: `outlineView.setDropItem(dropTargetNode, dropChildIndex: updatedIndex)`.
Hovering a feed over another feed retargets to its parent folder. The user never sees an
invalid-highlight dead zone. The non-local path falls back to the default account, so a
drop is always acceptable *somewhere*.

**A19. The insertion index is predicted, so the indicator never lies.**
The dragged payload is wrapped in a throwaway `Node`, the children are
`sortedAlphabeticallyWithFoldersAtEnd()`, and `firstIndex` is read back out. The line
appears where the item will actually land.

**A20. Copy vs move is a first-class distinction, declared up front.**
`setDraggingSourceOperationMask([.move, .copy], forLocal: true)` in `viewDidLoad`;
`localDragOperation` then reads the option key at *both* validate and accept time. And
cross-account is **always `.copy`** — you cannot accidentally move a feed out of one
account into another.

**A21. The payload carries its parent.**
`pasteboardWriterForItem` sets `feedWriter.containerID = parentContainerID`. The
receiving side knows where the item came *from*, not just what it is — which is what
makes an unambiguous move possible.

**A22. Every failure branch surfaces.**
The move is bracketed by `BatchUpdate.shared.start()` / `.end()`, and every error path
calls `NSApplication.shared.presentError(error)`. There is no silent-failure branch in
the drop pipeline.

### Keyboard and commands

**A23. Shortcuts are data, not a switch statement.**
`Keyboard/SidebarKeyboardDelegate.swift` loads `SidebarKeyboardShortcuts.plist` into a
`Set<KeyboardShortcut>`. Adding a binding edits a plist.

**A24. Next/previous-unread skips intelligently.**
`nextSelectableRowWithUnreadArticle(wrappingToTop:)` composes `shouldSkipRow`,
`rowIsGroupItem`, `rowIsExpandedFolder`, `rowHasAtLeastOneUnreadArticle`. An expanded
folder is skipped because its children will be visited; a collapsed one is not.

**A25. Deletion is undoable.**
`deleteNodes(_:)` runs through `UndoableCommandRunner` with
`var undoableCommands = [UndoableCommand]()` on the controller.

**A26. The system's sidebar icon-size preference is observed.**
A `DistributedNotificationCenter` observer for `.appleSideBarDefaultIconSizeChanged`.
Change the setting in System Settings and NNW's rows re-rhythm live.

---

## (b) Gap analysis against Fichero's current sidebar

Fichero is genuinely ahead on several axes NNW does not attempt: native multi-select via
`List(selection: Binding<Set<SidebarDestination>>)` with `.tag(item.destination)`
(`SidebarView+ViewComponents.swift:51`), Open in New Tab / New Window
(`SidebarItemRow+Presentation.swift:12`), a selection-aware Run Workflow submenu via
`WorkflowRunTargetResolver.resolve(clicked:selection:documents:)`, and option-click
expand-subtree (`SidebarItemRow.swift:216`). The gaps below are real, but they sit on top
of a more capable base.

| # | Axis | NetNewsWire | Fichero today | Verdict |
|---|---|---|---|---|
| B1 | Row metrics | One `SidebarCellAppearance` struct (A1) | **Five** independent recipes: `SidebarItemRow.swift:237` `.padding(.vertical, 1)`; `SidebarView+UnifiedRows.swift:199` insets `(0,12,0,8)`; UnifiedLibrarySections `(2,8,2,8)`; PinnedNavigationRows leading 16/16/16/16/24/8 with tops 2/0/0/6/0/4; `SidebarSectionHeader.swift:46` `.padding(.vertical, 2)` | **Gap.** Rows in different sections do not share a rhythm. |
| B2 | Counts / badges | `UnreadCountView` w/ macOS 26 branch (A3) | **Zero `.badge(` in `Views/Sidebar/`.** Counts exist only in `SidebarSectionHeader.swift:110` | **Gap.** Biggest visual win available. |
| B3 | Title vs count collision | Title clamped to badge (A2) | No clamp — nothing to clamp against yet | **Gap, blocked on B2.** |
| B4 | Hover | Not applicable (AppKit hover is manual) | **Zero `.onHover` in `Views/Sidebar/`** | **Gap.** No row responds to the cursor. |
| B5 | Icon tinting | One `backgroundStyle` hook (A4) | Per-call-site; `Image(systemName:).frame(width: 16, alignment: .center)` (#1015) | Minor gap. |
| B6 | Semantic fonts | Uses `NSFont` metrics (AppKit-normal) | Mostly semantic, but `SidebarItemRow+Label.swift` has `.font(.system(size: 11, weight: .bold))` on the ingest badge with a 13pt `Circle` at `.offset(x: 4, y: 4)` | **Existing rule violation in-tree.** |
| B7 | Restoration | One `SidebarWindowState`, restored as a unit (A9/A10) | **Split.** Expansion in `SidebarState` (`UserDefaults`, per window id); selection in `@SceneStorage`; reconciled *afterwards* by `reconcileRestoredSelection()`, called from both `.task` and the `librariesLoadVersion` `onChange`. `sidebarShouldReconcileSelection` exists precisely because the two halves can disagree (#2548) | **Biggest structural gap.** |
| B8 | Filter safety | Filter exceptions keep selection visible (A11) | `sidebarFilterText` + `filteredLibraryHeaders`, no exception mechanism. The new bottom-toolbar filter (#4061) **can filter the selected row out of view** | **Gap with a live bug behind it.** |
| B9 | Selection veto | `selectionIndexesForProposedSelection` (A12) | None — SwiftUI has no equivalent hook | **Gap, not directly closable.** Needs a settle-in-the-setter approach. |
| B10 | Rebuild coalescing | `CoalescingQueue(interval: 1.0)` (A13) | `sidebarTreeSignatures: [UUID: Int]` hash-compare (#3862) | **Fichero is arguably better** — content-addressed rather than time-windowed. |
| B11 | Surgical updates | `applyToCellsForRepresentedObject` (A14) | `cachedLibraryItemBuckets` + stable `ForEach(id: \.element.id)`; SwiftUI diffs per row | **Parity by different means.** |
| B12 | Context menus | Two menus, count-aware (A15) | **One** `rowContextMenu`. Run Workflow *is* selection-aware; nothing else is | **Gap.** |
| B13 | Mixed payloads | Rejected outright (A16) | **Silently narrowed:** `droppedIds.filter { $0.hasPrefix("doc:") }` (`SidebarView+UnifiedRows.swift:227`) | **Gap + rule violation** ("prefer raise over silent fallback"). |
| B14 | Payload taxonomy | Classified once, routed by shape (A17) | `sidebarUnifiedRowsReorderKind(items:source:destination:)` is the right shape — but guards **`.onMove` only**, not `.dropDestination` | **Half-built.** |
| B15 | Drop retargeting | `setDropItem` walks to legal ancestor (A18) | None. This is #3390 — "no visual drop indication and does not drop" | **Gap, maps to an open issue.** |
| B16 | Insertion index | Predicted from sorted children (A19) | Offset taken from `.dropDestination` verbatim | Gap. |
| B17 | Copy vs move | Option = copy; cross-account always copy (A20) | Move only. Cross-library is #2397 (open) | **Gap, maps to an open issue.** |
| B18 | Payload contents | Carries `containerID` (A21) | `SidebarDragID { let id: String }` — id alone | **Gap; blocks a clean cross-library move.** |
| B19 | Error surfacing | `presentError` on every branch (A22) | **Inconsistent with itself.** `handleExternalInsertionDrop` sets `sidebarState.dropErrorMessage`; but `reorderSavedSearchRows` and `reorderWorkflowRows` both `try?`-swallow (lines 153–154, 165) | **Gap + rule violation.** |
| B20 | Duplicate-drop check | `nodeHasChildRepresentingAnyDraggedFeed` | `SidebarMovePolicy.isValidTarget` catches **cycles**, shared between menu and drop (#3014) — but no duplicate-identity check | Gap. |
| B21 | Item identity | Gated on *type* (`representedObject is Folder`) | Gated on an **icon string**: `var isInboxFolder: Bool { item.icon == "tray.fill" }`, and `.draggable(item.icon == "tray.fill" ? …)` | **Design smell.** A cosmetic change to an icon changes drag behaviour. |
| B22 | Prefetch before paint | `prefetchFeedIcons()` (A8) | `disclosureContent` falls back to `Color.clear.frame(height: 0.5)` to hold the chevron during lazy load (#3355) — a *placeholder*, not a prefetch | Gap against "Every Frame Perfect". |
| B23 | Group headers | Separate cell path (A7) | `SidebarSectionHeader` exists; `.listRowSeparator(.hidden)` applied **only** to pinned rows | Minor gap (inconsistency). |
| B24 | De-indented top level | `frameOfCell` override (A5) | Pinned global rows at the bottom (#1456) with ad-hoc leading insets 16/16/16/16/24/8 | Gap — the ad-hoc insets *are* an attempt at this. |
| B25 | Idle chrome | Bar slides fully away (A6) | `var shouldShowBottomToolbar: Bool { true }` — hardcoded, always present | Deliberate (#4061 owns the filter field). Not a gap. |
| B26 | Keyboard | plist-driven (A23), next-unread nav (A24) | `.onDeleteCommand`, `.onExitCommand` collapse-to-anchor, native shift+arrow | Parity for an archive. No unread axis exists. |
| B27 | Undo | `UndoableCommandRunner` (A25) | `@Environment(\.undoManager)` is read in `SidebarView`; delete goes through `deleteState` + alerts | Unverified — worth a check, out of scope here. |
| B28 | System icon-size pref | Distributed notification (A26) | None | Low value; `.listStyle(.sidebar)` may already track it. |

---

## (c) Adoptable ideas, ranked by visual impact per unit of effort

**C1. `.badge()` on count-bearing rows.** *(from A3; closes B2/B3)*
`.badge(count)` on the row. Native macOS 26 rendering *is* NNW's macOS 26 treatment:
secondary label, monospaced digits, no pill, white on selection, hidden at zero. It also
resolves B3 for free — the system reserves the trailing space, so no manual clamp is
needed.
*Rules:* satisfies semantic-fonts (no explicit size at all). Counts must be real, not
capped — no `99+`, per show-ALL-items. Feeds one number per row, so no wholesale
re-render.
*Effort:* one modifier per row kind. **Highest ratio in the review.**

**C2. One `SidebarRowMetrics` struct.** *(from A1/A2; closes B1)*
A single `struct SidebarRowMetrics { static let insets: EdgeInsets; static let iconWidth: CGFloat; … }`
consumed by every row and header. Consolidates the five recipes in B1.
*Rules:* pure consolidation, no behaviour change; guarded by the existing
`Sidebar*Tests.swift` suite and `scripts/check_sidebar_items.py`.
*Effort:* low, mechanical, high visual payoff (rows finally share a rhythm).

**C3. Hover affordance.** *(closes B4; also closes #2496)*
`.onHover` on the row → a subtle background fill, reusing the existing
`sidebarDropHighlight` machinery at a lower opacity. #2496 ("hard to click-to-select,
must drag from below") is at root a *feedback* bug: nothing tells you the row is live.
The full-width hit region already exists (`fullWidthLabel`, `.contentShape(Rectangle())`).
*Rules:* ON, not a toggle. One row's state changes, not the list.
*Effort:* low.

**C4. Fix the ingest-badge font.** *(closes B6)*
`.font(.system(size: 11, weight: .bold))` → a semantic style. This is a standing
hard-rule violation sitting in the tree. Note the *deliberate* exceptions from the
"blanket font sweep is wrong" memory do not cover this case: the badge is not display
type, not conditional sizing — it is a small bold label.
*Effort:* trivial. Should ride along with C1, which touches the same visual slot.

**C5. Filter exceptions.** *(from A11; closes B8)*
When `sidebarFilterText` is non-empty, keep the selected destination *and its ancestor
chain* in `filteredLibraryHeaders` regardless of match. In SwiftUI this is a predicate
change in the filter, not a separate mechanism: `matches(item) || isSelected(item) || isAncestorOfSelection(item)`.
*Rules:* dead-simple UX — no toggle, it is just correct. Directly protects #4061.
*Effort:* low. Fixes a live bug.

**C6. Unify restoration into one `SidebarWindowState`.** *(from A9/A10; closes B7)*
One `Codable` value with `expandedItems`, `selectedDestinations`, `filterText`, persisted
per window id, applied in one function in NNW's order: expand defaults → overlay saved
expansion → apply selection in one write → apply filter. That removes the need for
`reconcileRestoredSelection()` and `sidebarShouldReconcileSelection` entirely, which is
the #2548 fragility.
*Rules:* touches the observable data layer; needs restoration tests (fresh launch, saved
state, saved state naming a since-deleted item, library-loads-after-restore).
*Effort:* **medium-high, and the highest-value structural change.** Not a visual win —
sequence it after the visual batch.

**C7. Real drop validation: taxonomy → legality → retarget → predicted index.**
*(from A16–A19; closes B13/B14/B15/B16/B20, and #3390)*
Four steps, adoptable independently and in this order:
 1. Promote `sidebarUnifiedRowsReorderKind` to classify the **drop** payload too, and
    **reject** mixed payloads instead of `filter { $0.hasPrefix("doc:") }`.
 2. Compute the legal target by walking up the ancestor chain — SwiftUI has no
    `setDropItem`, so this becomes "the drop handler resolves the effective target and
    the highlight renders on *that* row." That is the translation, and it is the part
    with no free equivalent.
 3. Predict the insertion index by applying the move to a copy of the children and
    reading back the resulting position.
 4. Add the duplicate-identity check alongside the existing cycle check in
    `SidebarMovePolicy`.
*Rules:* raise, never silently narrow. Shares one decision between menu and drop, as
#3014 established.
*Effort:* medium-high. **This is where #3390 actually gets fixed** — the current issue
is not a missing highlight, it is a missing validation model.

**C8. Surface every drop/reorder failure.** *(from A22; closes B19)*
Replace the two `try?` swallows in `reorderSavedSearchRows` / `reorderWorkflowRows` with
the `sidebarState.dropErrorMessage` path `handleExternalInsertionDrop` already uses. The
sidebar currently disagrees with itself about whether failures are visible.
*Effort:* trivial. Pure rule compliance.

**C9. Cross-library drag is a copy, and the payload carries its parent.**
*(from A20/A21; closes B17/B18, and #2397)*
Extend `SidebarDragID` to `{ id, parentId, libraryId }`. Same-library → move;
cross-library → copy, always, no modifier required. `.visibility(.ownProcess)` is
preserved (#623/#711 depend on it).
*Effort:* medium. Unblocks #2397, which is otherwise not cleanly implementable — you
cannot safely move an item whose origin the payload does not name.

**C10. Type-based identity instead of icon-string identity.** *(closes B21)*
`isInboxFolder` and the `.draggable` guard should read a `SidebarItem` property
(`isProtectedRoot` or similar), not `item.icon == "tray.fill"`. Today, restyling an icon
silently changes drag behaviour.
*Effort:* low. Best done as part of C7.

**C11. Two context menus.** *(from A15; closes B12)*
When the right-clicked row is outside the current selection, build the menu for the
clicked row (and select it, Finder-style); when inside, build for the whole selection.
Run Workflow already does exactly this via `WorkflowRunTargetResolver` — generalise that
resolver's shape to the rest of the menu.
*Effort:* medium.

**C12. Prefetch children/icons before the row paints.** *(from A8; closes B22)*
On expand, resolve children *then* animate open, rather than opening onto a
`Color.clear.frame(height: 0.5)` placeholder. Straight "Every Frame Perfect" work.
*Effort:* medium; interacts with the #3355 lazy-load path. **Adjacent to #4058's lane —
coordinate before starting.**

**C13. De-indent top-level pinned rows properly.** *(from A5; closes B24)*
Fold the ad-hoc 16/16/16/16/24/8 leading insets into C2's metrics struct as one
explicit `topLevelLeading` value. The current numbers are an undocumented attempt at
exactly NNW's `frameOfCell` override.
*Effort:* low, once C2 exists.

**Not worth doing now:** A23 (plist-driven shortcuts — Fichero's binding set is small and
`.onDeleteCommand`/`.onExitCommand` are already declarative); A26 (system icon-size
notification — `.listStyle(.sidebar)` likely tracks it already; verify before building);
A13's time-window coalescing (Fichero's signature-hash approach in #3862 is better).

### Literal-code notes

Two places where lifting NNW code verbatim would be tempting, both requiring the MIT
attribution to be reproduced in the receiving file's header:

- **`SidebarCellLayout`'s title-clamp arithmetic** (A2). *Recommendation: do not lift.*
  `.badge()` makes it unnecessary — the system reserves the trailing space.
- **`localDragOperation`'s copy/move decision table** (A20). *Recommendation: do not
  lift.* It is ~15 lines of `if` over NNW's account model; Fichero's rule
  ("cross-library is always copy") is one line and reads better.

Everything else proposed here is an idea, not code. No attribution obligation arises.

---

## (d) What NOT to copy

**D1. The unread-count *concept*, as a domain model.** NNW's unread count is the spine of
its UI — it drives next-unread navigation, the read filter, smart feeds, and the badge.
An archive has no "unread." Adopt `.badge()` as a *number-bearing affordance* (child
count, match count, pending-ingest count) and stop there. Do not import a read/unread
state axis into a research tool.

**D2. `nodeRepresentsDraggableItem`'s feed/folder-only universe.** NNW has two draggable
types. Fichero has documents, folders, saved searches, workflows, chats, comparisons,
schedules, triggers. The *taxonomy pattern* (A17) transfers; the specific two-case enum
does not.

**D3. `violatesDisallowFeedInRootFolder` / `…CopyInRootFolder` / `…InMultipleFolders`.**
Gated on `account.behaviors.contains(...)` — these encode Feedly and Google-Reader API
restrictions. Only the *shape* is adoptable: backend-declared capabilities decide drop
legality, rather than the client hardcoding rules. The policies themselves are meaningless
for a local DuckDB library.

**D4. The read filter as a user-facing toggle.** `isReadFiltered` + `toggleReadFilter()`
is a persisted user preference. Fichero's rule is features ON or OFF, not a pile of
switches, and #4061 already gives the sidebar one filter field. Adopt the *filter
exceptions* (C5) without the toggle.

**D5. `selectionIndexesForProposedSelection` as an architecture.** No SwiftUI equivalent
exists — you cannot veto a proposed `List` selection. Fichero's `sidebarSelectionBinding`
setter can *settle* a selection after the fact (it already derives the primary
destination there), but a true pre-emptive veto would mean dropping to `NSViewRepresentable`
over an `NSOutlineView`. Not worth it. Prevent bad selections structurally instead — make
headers non-selectable rather than un-selecting them.

**D6. `applyToCellsForRepresentedObject` and the whole cell-reuse layer.** This is
`NSTableView` cell recycling. SwiftUI's `ForEach` with stable `id` plus `@Observable`
already delivers the same guarantee (Fichero's "no wholesale list re-render" rule).
Reproducing it would mean fighting the framework.

**D7. `frameOfCell(atColumn:row:)` as a mechanism.** The de-indent *effect* (C13) is worth
having; the override is not available. Use a metrics value.

**D8. `RowSizeStyle` / three-tier icon sizing.** NNW supports 16/19/22pt because it
back-deploys across many macOS versions and honours a legacy sidebar preference. Fichero
is Golden Gate only; `.listStyle(.sidebar)` handles this.

**D9. `NSSecureCoding` for window state.** `Codable` is the modern equivalent (C6). Do
not import `NSSecureCoding` ceremony.

**D10. `restoreLegacyState(from:)`.** A migration path for NNW's own old format. Fichero
has no legacy sidebar-state format to migrate from.

**D11. NNW has no analogue for #2498** (iOS/iPad shows one open library, Mac shows two).
NNW assumes a single flat account list on both platforms. That issue is platform-IA work
and this review has nothing to contribute to it.

---

## (e) Proposed issue set

Ordered. Visual batch first (fast, high-impact, low-risk, all independently landable),
then the structural work. **Not filed.**

**1. Sidebar: adopt native `.badge()` for count-bearing rows.**
Add `.badge()` to sidebar rows that carry a meaningful number — folder child counts,
saved-search match counts, pending-ingest counts. On macOS 26 the native badge renders
exactly the treatment NetNewsWire hand-builds in `UnreadCountView.swift`: no drawn pill,
`.secondaryLabelColor`, monospaced digits, inverted to white on selection, and absent at
zero. Because the system reserves trailing space for the badge, the title truncates
around it automatically — no manual clamp needed. Counts must be real values with no
`99+` cap, per show-ALL-items. There is currently zero `.badge(` usage anywhere in
`Views/Sidebar/`; counts appear only in `SidebarSectionHeader.swift:110`. Highest visual
return per unit of effort in the whole review.

**2. Sidebar: consolidate five row-metric recipes into one `SidebarRowMetrics`.**
Row geometry is defined independently in five places — `SidebarItemRow.swift:237`
(`.padding(.vertical, 1)`), `SidebarView+UnifiedRows.swift:199` (insets `0,12,0,8`),
UnifiedLibrarySections (`2,8,2,8`), PinnedNavigationRows (leading 16/16/16/16/24/8, tops
2/0/0/6/0/4), and `SidebarSectionHeader.swift:46`. Rows in different sections therefore
do not share a vertical rhythm. NetNewsWire's `SidebarCellAppearance.swift` is a single
`Equatable` metrics struct that every cell reads, which is why its sidebar reads as one
surface. Introduce one `SidebarRowMetrics` consumed by every row and header, folding the
pinned rows' ad-hoc leading insets into an explicit `topLevelLeading` value (NetNewsWire
achieves the same de-indent by overriding `frameOfCell(atColumn:row:)`). Pure
consolidation, no behaviour change.

**3. Sidebar: add a hover affordance to rows (fixes #2496).**
There is no `.onHover` anywhere in `Views/Sidebar/` — no row responds to the cursor at
all. #2496 ("list items hard to click-to-select, must drag from below") is fundamentally
a feedback bug rather than a hit-testing one: the full-width hit region already exists
via `fullWidthLabel` and `.contentShape(Rectangle())`, but nothing indicates the row is
live before you commit to a click. Add a subtle hover background, reusing the existing
`sidebarDropHighlight` overlay at lower opacity for visual consistency with the drop
state. Always on, not a preference.

**4. Sidebar: replace the hardcoded ingest-badge font with a semantic style.**
`SidebarItemRow+Label.swift` sets `.font(.system(size: 11, weight: .bold))` on the ingest
badge with a 13pt `Circle` at `.offset(x: 4, y: 4)`. This violates the standing
semantic-system-fonts rule and is not one of the intentional exceptions (it is neither
display type, weighted headline treatment, nor conditional sizing — it is a small bold
label). Replace with a semantic style and let the circle size derive from it. Best landed
alongside issue #1, which touches the same visual slot.

**5. Sidebar: filtering must never hide the selected row or its ancestors.**
The bottom-toolbar filter field (#4061) filters `filteredLibraryHeaders` by
`sidebarFilterText` with no exemption for the current selection, so typing into it can
filter the selected row out of view — leaving the detail pane showing an item with no
corresponding sidebar row. NetNewsWire solves this with *filter exceptions*
(`addAllSelectedToFilterExceptions` / `addToFilterExceptionsIfNecessary` /
`addParentFolderToFilterExceptions`): under its read filter, the selected item and its
parent folder are exempt, re-seeded on every rebuild and reset immediately after so they
never accumulate. In SwiftUI this is a predicate change, not a new mechanism: keep an
item when it matches the filter, is selected, or is an ancestor of the selection.

**6. Sidebar: surface reorder failures instead of swallowing them.**
`reorderSavedSearchRows` and `reorderWorkflowRows` in `SidebarView+UnifiedRows.swift`
(lines 153–154 and 165) both wrap their service calls in `try?`, so a failed reorder
leaves the sidebar showing an order the backend rejected, with no indication. This
violates the prefer-raise-over-silent-fallback rule, and the sidebar disagrees with
itself: `handleExternalInsertionDrop` in the same file *does* surface failure via
`sidebarState.dropErrorMessage`. NetNewsWire calls
`NSApplication.shared.presentError(error)` on every failure branch in its drop pipeline.
Route both reorder paths through the existing `dropErrorMessage` surface.

**7. Sidebar: reject mixed drag payloads instead of silently narrowing them.**
`handleExternalInsertionDrop` reduces the payload with
`droppedIds.filter { $0.hasPrefix("doc:") }`, so dragging a mixed selection of documents
and workflows silently drops the workflows and moves only the documents — the user sees a
partial result with no explanation. NetNewsWire refuses outright when a drag mixes kinds,
and classifies the payload exactly once into a typed shape before any validator runs
(`DraggedFeedsContentsType`). Fichero already has the right helper in
`sidebarUnifiedRowsReorderKind(items:source:destination:)`, but it guards `.onMove` only,
not `.dropDestination`. Promote it to classify drop payloads too, and reject mixed drags.

**8. Sidebar: identify protected/undraggable rows by type, not by icon string.**
`isInboxFolder` is `item.icon == "tray.fill"`, and the row's `.draggable` modifier
branches on that same string comparison — so restyling an icon silently changes drag
behaviour. NetNewsWire gates every equivalent decision on the represented object's *type*
(`representedObject is Folder`, `node.canHaveChildNodes`). Add an explicit `SidebarItem`
property (e.g. `isProtectedRoot`) set by `SidebarItemBuilder.buildInboxItem` and read
everywhere the icon string is currently compared.

**9. Sidebar: real drop validation with target retargeting and a predicted insertion index (fixes #3390).**
#3390 ("PDF drag-and-drop has no visual drop indication and does not drop") is not a
missing-highlight bug — the sidebar has no drop-validation model. NetNewsWire's has four
stages: classify the payload once; decide legality; **retarget** an illegal target by
walking up to the nearest legal container and rewriting the drop item
(`ancestorThatCanAcceptLocalFeed` → `setDropItem(_:dropChildIndex:)`), so hovering a
document over another document silently retargets to its parent folder rather than showing
a dead zone; and **predict** the insertion index by wrapping the payload in a throwaway
node, re-sorting the children, and reading back the resulting position, so the indicator
never lies. SwiftUI has no `setDropItem`, so retargeting becomes: the drop handler resolves
the effective target and the highlight renders on *that* row. Also add the missing
duplicate-identity check alongside the existing cycle check in `SidebarMovePolicy` — today
dropping an item into a folder that already contains it is accepted. Depends on #7.

**10. Sidebar: cross-library drag is a copy, and the payload carries its parent (fixes #2397).**
`SidebarDragID` carries `{ let id: String }` and nothing else, so the receiving side knows
what was dragged but not where it came from — which is why #2397 ("can't drag-and-drop to
move an item from one library to another") is not cleanly implementable today.
NetNewsWire's pasteboard writer injects the source container
(`feedWriter.containerID = parentContainerID`), and its `localDragOperation` makes
cross-account drags **always** `.copy`, never a move, so an item cannot silently leave one
account for another. Extend `SidebarDragID` to carry `parentId` and `libraryId`; same-library
drags stay moves, cross-library drags become copies with no modifier required. Preserve
`.visibility(.ownProcess)` — #623 and #711 both depend on it. Depends on #9.

**11. Sidebar: unify expansion, selection, and filter state into one restorable value.**
Expansion lives in `SidebarState` (`UserDefaults`, per window id) while selection lives in
`@SceneStorage`; they are restored separately and reconciled afterwards by
`reconcileRestoredSelection()`, called from both `SidebarView.task` and the
`librariesLoadVersion` `onChange`. The helper `sidebarShouldReconcileSelection` exists
precisely because the two halves can disagree — the #2548 fragility. NetNewsWire restores
all of it as one `SidebarWindowState` (`isReadFiltered`, `expandedContainers`,
`selectedFeeds`), *computed* on demand rather than incrementally maintained, and applied in
one function in a deliberate order: expand top-level defaults first, overlay saved
expansion, then a single batched `selectRowIndexes`, then focus, then the filter state.
Adopting that shape removes the reconcile step entirely. Needs restoration tests: fresh
launch, saved state, saved state naming a since-deleted item, and library-loads-after-restore.
Largest structural change in this review; sequence after the visual batch.

**12. Sidebar: two context menus — one for the selection, one for a clicked row outside it.**
There is a single `rowContextMenu`, so right-clicking a row outside a multi-row selection
offers actions scoped to the clicked row while the visible highlight says otherwise.
NetNewsWire keeps `contextualMenuForSelectedObjects()` and `contextualMenuForClickedRows()`
distinct, and its `menu(for objects:)` switches on *count* first — no-selection, multiple,
single — so a 12-row selection gets a menu built for 12 rows rather than a single-row menu
with plural verbs. Fichero already does this correctly for one entry: Run Workflow resolves
its targets through `WorkflowRunTargetResolver.resolve(clicked:selection:documents:)`.
Generalise that resolver's shape to the rest of the menu.

**13. Sidebar: resolve children before the disclosure animates open.**
Expanding a folder currently opens onto a `Color.clear.frame(height: 0.5)` placeholder that
exists solely to keep the chevron visible while children load (#3355), so the user sees an
empty expanded row before content arrives. NetNewsWire prefetches icons for all
about-to-be-visible feeds before they draw — from `viewDidLoad`, from every tree rebuild,
and again on `outlineViewItemDidExpand` — so a newly revealed row has its content in hand
before first paint. Resolve (or cache-check) children first, then animate open. Straight
"Every Frame Perfect" work. **Note:** touches the lazy-child-load path adjacent to #4058;
coordinate with that lane before starting.
