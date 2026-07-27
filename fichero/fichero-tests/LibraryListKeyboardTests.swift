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
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
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

    @Test("selected+focused rows invert to white-on-accent")
    func selectedRowsInvert() throws {
        let source = try appSource("Views/Library/LibraryViewComponents.swift")
        #expect(source.contains("isSelected && isPaneFocused"))
        #expect(source.contains("primaryTextColor"))
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

    @Test("entity lozenge block reserves real height while loading")
    func lozengeReservation() throws {
        let source = try appSource("Views/Inspector/Artifacts/ArtifactEntityViews.swift")
        #expect(!source.contains("style == .singleLine ? 14 : 1)"),
                "1pt multiLine reservation = relayout-on-load (#4160)")
    }
}
