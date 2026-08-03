@testable import Fichero
import Foundation
import Testing

/// #4160 step 1: list-view keyboard/selection correctness. The old code used
/// `selection.first` (Set hash order) as the keyboard cursor, so after any
/// multi-select the arrows resumed from, Return opened, and the follow-scroll
/// targeted an arbitrary row.
struct LibraryKeyboardCursorTests {
    private let ids = ["a", "b", "c", "d", "e"]

    @Test("explicit cursor wins when still selected")
    func cursorWins() {
        let idx = LibraryKeyboardCursor.index(
            cursor: "d", anchor: "b", selection: ["b", "c", "d"], ids: ids
        )
        #expect(idx == 3)
    }

    @Test("stale cursor (deselected) falls back to the anchor")
    func staleCursorFallsBack() {
        let idx = LibraryKeyboardCursor.index(
            cursor: "e", anchor: "b", selection: ["b", "c"], ids: ids
        )
        #expect(idx == 1)
    }

    @Test("no cursor/anchor resolves to the TOPMOST selected row, not hash order")
    func topmostFallback() {
        let idx = LibraryKeyboardCursor.index(
            cursor: nil, anchor: nil, selection: ["d", "b", "e"], ids: ids
        )
        #expect(idx == 1)
    }

    @Test("empty selection has no cursor")
    func emptySelection() {
        #expect(LibraryKeyboardCursor.index(cursor: nil, anchor: nil, selection: [], ids: ids) == nil)
    }

    @Test("ids missing from the visible list are ignored")
    func hiddenIdsIgnored() {
        let idx = LibraryKeyboardCursor.index(
            cursor: "zz", anchor: "zz", selection: ["zz", "c"], ids: ids
        )
        #expect(idx == 2)
    }
}

/// Source-surface guards for the list-mode fixes, mirroring
/// `ShellLayoutGuardTests` — deterministic, no running app.
struct LibraryListModeGuardTests {
    private func appSource(_ relativePath: String) throws -> String {
        let url = try AppSource.root()
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    @Test("list mode claims focus so onKeyPress receives keys")
    func listModeIsFocusable() throws {
        let source = try appSource("Views/Library/ViewModes/LibraryView+ListView.swift")
        #expect(source.contains(".focusable()"))
        #expect(source.contains(".focusEffectDisabled()"))
    }

    @Test("list mode consumes the double-click center target")
    func centerTargetConsumed() throws {
        let source = try appSource("Views/Library/ViewModes/LibraryView+ListView.swift")
        #expect(source.contains("listScrollCenterTarget"))
    }

    @Test("no Set-hash-order cursor reads remain in keyboard paths")
    func noHashOrderCursor() throws {
        // IconMode/TableView were originally EXCLUDED from this loop — which
        // is exactly why their copies of the bug survived step 1 (audit G1/G2).
        for path in [
            "Views/Library/LibraryView+ArrowNavigation.swift",
            "Views/Library/ViewModes/LibraryView+ListView.swift",
            "Views/Library/ViewModes/LibraryView+IconMode.swift",
            "Views/Library/ViewModes/LibraryView+TableView.swift",
            "Views/Library/LibraryView+DeleteActions.swift",
            "Views/Library/LibraryView+KeyboardShortcuts.swift"
        ] {
            let source = try appSource(path)
            #expect(!source.contains("selection.first"), "selection.first is hash order — use LibraryKeyboardCursor (\(path))")
        }
        // Return-to-open acts on the ordered primary and matches double-click.
        let deleteActions = try appSource("Views/Library/LibraryView+DeleteActions.swift")
        #expect(deleteActions.contains("orderedPrimarySelectionId"))
        #expect(deleteActions.contains("openDocument(doc)"))
    }

    @Test("shift-extend never re-anchors on the moving end")
    func shiftAnchorStable() throws {
        let source = try appSource("Views/Library/LibraryView+ArrowNavigation.swift")
        #expect(source.contains("the anchor NEVER moves during a"))
        #expect(!source.contains("selection.insert(targetId)"))
    }

    @Test("selection is Mail-style: grey fill + accent label, no inversion")
    func selectedRowsUseMailStyle() throws {
        // #4191 — the #4160 white-on-accent inversion is GONE (it existed
        // only because black-on-solid-accent was illegible); the shared
        // treatment is a subtle grey fill with the focus split in the label.
        let components = try appSource("Views/Library/LibraryViewComponents.swift")
        #expect(components.contains("enum LibrarySelectionStyle"))
        #expect(components.contains("unemphasizedSelectedContentBackgroundColor"))
        #expect(components.contains("LibrarySelectionStyle.labelTint(focused: isPaneFocused)"))
        #expect(!components.contains("invertsText"))
        #expect(!components.contains(".white"))

        // The row fill is the constant grey; tint stays in the == comparison
        // so focus flips still re-render selected rows.
        let helpers = try appSource("Views/Library/ViewModes/LibraryView+Helpers.swift")
        #expect(helpers.contains("LibrarySelectionStyle.fill"))
        let list = try appSource("Views/Library/ViewModes/LibraryView+ListView.swift")
        #expect(list.contains("tint: selectionTint"))
    }

    @Test("rows and tiles have uniform density: reserved lines + capped lozenges")
    func rowDensityIsUniform() throws {
        // #4191 density cap — every list row / icon tile is the SAME height:
        // title and summary reserve fixed lines, the entity-lozenge block is
        // a fixed-height window matching its loading reservation, and tile
        // labels reserve two lines. Stable scroll + honest PageUp/Down.
        let components = try appSource("Views/Library/LibraryViewComponents.swift")
        #expect(components.contains(".lineLimit(2, reservesSpace: true)"))
        #expect(components.contains("static let entityBlockHeight: CGFloat = 40"))
        #expect(components.contains(".frame(height: Self.entityBlockHeight, alignment: .topLeading)"))
        #expect(!components.contains(".lineLimit(4)"))
        #expect(!components.contains(".lineLimit(3)"))

        let tiles = try appSource("Views/Library/LibraryThumbnailViews.swift")
        #expect(tiles.contains(".lineLimit(2, reservesSpace: true)"))
    }

    @Test("list rows support inline rename via the shared editable name")
    func inlineRenameWired() throws {
        let components = try appSource("Views/Library/LibraryViewComponents.swift")
        #expect(components.contains("EditableDocumentName("))
        // Rename state must reach the .equatable() diff or the field never
        // appears — the one place these changes can silently break (audit).
        let helpers = try appSource("Views/Library/ViewModes/LibraryView+Helpers.swift")
        #expect(helpers.contains("var isRenaming: Bool"))
        let list = try appSource("Views/Library/ViewModes/LibraryView+ListView.swift")
        #expect(list.contains("isRenaming: renamingDocumentId == doc.id"))
    }

    @Test("Space, Home, and End are handled")
    func spaceHomeEnd() throws {
        let keys = try appSource("Views/Library/LibraryView+KeyboardShortcuts.swift")
        #expect(keys.contains(".onKeyPress(.space)"))
        #expect(keys.contains(".onKeyPress(.home"))
        #expect(keys.contains(".onKeyPress(.end"))
        #expect(keys.contains(".quickLookPreview($quickLookURL)"))
    }

    @Test("list rows prefetch thumbnails and carry accessibility")
    func prefetchAndAccessibility() throws {
        let list = try appSource("Views/Library/ViewModes/LibraryView+ListView.swift")
        #expect(list.contains("scheduleThumbnailPrefetch(around: doc.id)"))
        let components = try appSource("Views/Library/LibraryViewComponents.swift")
        #expect(components.contains(".accessibilityElement(children: .combine)"))
        #expect(components.contains("accessibilityIdentifier(\"libraryRow."))
    }

    @Test("icon tiles match the list-row bar: rename, a11y, hover, diffing")
    func iconTileParity() throws {
        let tiles = try appSource("Views/Library/LibraryThumbnailViews.swift")
        #expect(tiles.contains("EditableDocumentName("))
        #expect(tiles.contains("accessibilityIdentifier(\"libraryTile."))
        #expect(tiles.contains("accessibilityIdentifier(\"libraryEntityTile."))
        let icon = try appSource("Views/Library/ViewModes/LibraryView+IconMode.swift")
        #expect(icon.contains("LibraryIconCell("))
        #expect(icon.contains("isRenaming: renamingDocumentId == doc.id"))
        #expect(icon.contains("LibraryRowHoverWash"))
        // Empty-space click deselects, like Finder.
        #expect(icon.contains("selection.removeAll()"))
    }

    @Test("Quick Look is discoverable from the context menu")
    func quickLookInMenu() throws {
        let menu = try appSource("Views/Library/LibraryView+ContextMenu.swift")
        #expect(menu.contains("Label(\"Quick Look\""))
        let keys = try appSource("Views/Library/LibraryView+KeyboardShortcuts.swift")
        #expect(keys.contains("func quickLook(_ doc: Document)"))
    }

    @Test("table mode matches the list/icon bar: cursor, drag, a11y, hover")
    func tableModeParity() throws {
        let table = try appSource("Views/Library/ViewModes/LibraryView+TableView.swift")
        // Deterministic primary pick everywhere the native Table hands us a
        // Set — context menu, double-click, selection watcher (audit G1/G2).
        #expect(table.contains("func primaryNodeId(in items: Set<String>)"))
        #expect(!table.contains("items.first"))
        #expect(!table.contains("newSelection.first"))
        // The native Table writes selection directly; the shared cursor must
        // be maintained here or Return/Space act on the wrong row (G3).
        #expect(table.contains("selectionCursor = nodeId"))
        let columns = try appSource("Views/Library/ViewModes/LibraryView+TableColumns.swift")
        // The document row's modifiers live in `documentNameCell(for:)` since
        // #4202 split it out of `outlineNameCell` — same modifiers, so the
        // drag now reads `for: document` rather than `for: node.document`.
        #expect(columns.contains("func documentNameCell(for document: Document)"))
        #expect(columns.contains(".draggable(libraryItemDrag(for: document))"))
        #expect(columns.contains("libraryTableRow."))
        #expect(columns.contains("LibraryRowHoverWash"))
        // Thumbnails without prefetch = one image fetch per row on scroll (#4202).
        #expect(columns.contains("scheduleThumbnailPrefetch(around: document.id)"))
        // Child outline ids resolve to their parent doc for Return/Space (G2).
        let nav = try appSource("Views/Library/LibraryView+ArrowNavigation.swift")
        #expect(nav.contains("id.firstIndex(of: \":\")"))
        // Column layout persists (was window-lifetime @State — audit G5).
        let root = try appSource("Views/Library/LibraryView.swift")
        #expect(root.contains("@SceneStorage(\"library.tableColumns\")"))
    }

    @Test("entity lozenge block reserves real height while loading")
    func lozengeReservation() throws {
        let source = try appSource("Views/Inspector/Artifacts/ArtifactEntityViews.swift")
        #expect(!source.contains("style == .singleLine ? 14 : 1)"),
                "1pt multiLine reservation = relayout-on-load (#4160)")
    }
}
