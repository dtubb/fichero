import Foundation
import XCTest

@testable import Fichero

/// Modifier-grammar audit pins (2026-08-04). The Finder grammar — plain
/// in-app drag = MOVE, ⌥ = COPY, ⌘⌥ = ALIAS — is one pure function
/// (`sidebarDropOperation`) and one executor
/// (`applyLibraryItemDropOperation` / `sidebarApplyInsertionDropOperation`),
/// consulted by the sidebar row-onto-folder path, both insertion-line paths,
/// and the library folder cells. The audit found ONE surface ignoring it
/// (the library header always moved) and one dead always-move path
/// (`handleDropBesideItem`, zero callers). These pins keep the audit's
/// outcome true.
final class SidebarHeaderGrammarAndAliasStyleTests: XCTestCase {

    private func source(_ relativePath: String) throws -> String {
        try String(
            contentsOf: AppSource.root().appendingPathComponent(relativePath),
            encoding: .utf8
        )
    }

    /// The header speaks the grammar: modifiers sampled at the drop ENTRY
    /// point (the payload read is async; by resolution the keys are up), and
    /// non-move operations routed through the shared insertion executor at
    /// the library root.
    func testTheLibraryHeaderHonorsTheModifierGrammar() throws {
        let header = try source("Views/Sidebar/Sections/SidebarSectionHeader.swift")
        XCTAssertTrue(
            header.contains("SidebarDropModifiers.current()"),
            "the header stopped sampling modifiers at its drop entry point"
        )
        let helpers = try source("Views/Sidebar/Sections/SidebarView+LibraryHeaderHelpers.swift")
        XCTAssertTrue(
            helpers.contains("sidebarDropOperation(modifiers: modifiers, kind: .document)"),
            "the header item-drop stopped consulting the shared grammar"
        )
        XCTAssertTrue(
            helpers.contains("operation: operation, bareIds: bareIds, parentId: nil"),
            "non-move header drops must route through the shared insertion executor at root"
        )
    }

    /// The dead always-move sibling-reparent path stays dead. It ignored the
    /// grammar; resurrecting it would be the runWorkflowOnCollection shape —
    /// a scope path with no trigger, waiting to be wired to the wrong thing.
    func testTheBesideDropPathStaysDeleted() throws {
        let handlers = try source("Views/Sidebar/ItemRow/SidebarItemRow+DropHandlers.swift")
        XCTAssertFalse(
            handlers.contains("func handleDropBesideItem"),
            "handleDropBesideItem is back — it always moved, ignoring the modifier grammar"
        )
        XCTAssertFalse(handlers.contains("func performTransactionalSiblingReparent"))
    }

    /// Finder's alias grammar has two visual halves: the arrow badge AND the
    /// italic name (Daniel, 2026-08-04 — the badge alone is invisible at
    /// sidebar sizes). Pin both.
    func testAliasRowsRenderItalicWithTheArrowBadge() throws {
        let label = try source("Views/Sidebar/ItemRow/SidebarItemRow+Label.swift")
        XCTAssertTrue(
            label.contains(".italic(rowIsAlias)"),
            "the alias name lost its italic"
        )
        XCTAssertTrue(
            label.contains("arrowshape.turn.up.right.fill"),
            "the alias arrow badge is gone"
        )
    }

    /// The grammar itself, one more time, at the boundary the header uses.
    func testTheGrammarIsMoveCopyAlias() {
        XCTAssertEqual(
            sidebarDropOperation(optionHeld: false, commandHeld: false, kind: .document), .move
        )
        XCTAssertEqual(
            sidebarDropOperation(optionHeld: true, commandHeld: false, kind: .document), .copy
        )
        XCTAssertEqual(
            sidebarDropOperation(optionHeld: true, commandHeld: true, kind: .document), .alias
        )
        // ⌘ alone is not a grammar chord — plain move.
        XCTAssertEqual(
            sidebarDropOperation(optionHeld: false, commandHeld: true, kind: .document), .move
        )
    }
}
