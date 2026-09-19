@testable import Fichero
import FicheroAPIClient
import XCTest

/// spec: kg-tables — `kg.tables.entity.create` (hand-author an entity FROM the table,
/// not only via the Ontology sheet) + `crud.cross-surface` (a capability must reach the
/// UX, not sit in the backend/MCP/CLI only).
///
/// This is a capability-AVAILABILITY test (Testing Constitution): it pins that the
/// entities table surface actually wires the create path, so the affordance can't be
/// silently dropped while the backend/MCP create stays. It reads the surface's source —
/// the repo idiom for "this capability is present in this surface".
final class EntitiesTableCreateTests: XCTestCase {

    private static func appSource(_ relativePath: String) throws -> String {
        let url = try AppSource.root().appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    private func entitiesContentSource() throws -> String {
        try Self.appSource("Views/Library/ViewModes/Table/EntitiesLibraryContent.swift")
    }

    func testTableOffersAManualCreateAffordance() throws {
        let source = try entitiesContentSource()
        XCTAssertTrue(source.contains("New Entity"),
                      "the entities table must offer a New Entity affordance")
        XCTAssertTrue(source.contains("showingCreateSheet"),
                      "the create affordance must present the create sheet")
    }

    func testCreateReusesNewEntitySheetNotAParallelForm() throws {
        let source = try entitiesContentSource()
        XCTAssertTrue(source.contains("NewEntitySheet("),
                      "create must reuse the existing NewEntitySheet, not a new form")
    }

    func testCreatedEntityForcesAReloadOfThisScopeSoTheRowAppears() throws {
        let source = try entitiesContentSource()
        // #4885: a manual create must force-reload THIS view's actual scope
        // (folder-aggregated or library-wide) — not always the library-wide
        // list, which used to leave a folder-scoped table's new row invisible
        // until an unrelated library-wide refresh happened to fire.
        XCTAssertTrue(source.contains("await reloadScope(force: true)"),
                      "a manual create must force-reload this table's own scope")
    }

    func testTableOffersEditReusingTheSameSheet() throws {
        // Edit-from-table (spec) completes the entity CRUD trio; it reuses NewEntitySheet
        // in editing mode rather than a parallel editor.
        let content = try entitiesContentSource()
        XCTAssertTrue(content.contains("entityToEdit"),
                      "the table must hold an edit target")
        XCTAssertTrue(content.contains("NewEntitySheet(editing:"),
                      "edit must reuse NewEntitySheet in editing mode")
        let tableView = try Self.appSource("Views/Library/ViewModes/Table/EntitiesTableView.swift")
        XCTAssertTrue(tableView.contains("Edit…"),
                      "the entity row menu must offer an Edit affordance")
    }

    // MARK: - Inline rename (spec: entity.rename-inline)

    func testRenameNeverCommitsEmptyOrWhitespace() {
        XCTAssertNil(EntitiesTableView.sanitizedRename(""))
        XCTAssertNil(EntitiesTableView.sanitizedRename("   \n\t "))
        XCTAssertEqual(EntitiesTableView.sanitizedRename("  Quito "), "Quito")
        XCTAssertEqual(EntitiesTableView.sanitizedRename("Eugenio Córdoba"), "Eugenio Córdoba")
    }

    func testTableOffersInlineRename() throws {
        let tableView = try Self.appSource("Views/Library/ViewModes/Table/EntitiesTableView.swift")
        XCTAssertTrue(tableView.contains("Rename"),
                      "the entity row menu must offer a Rename affordance")
        XCTAssertTrue(tableView.contains("renamingId"),
                      "the Name cell must become an editable field for the row being renamed")
        XCTAssertTrue(tableView.contains("commitRename"),
                      "the inline field must commit the rename")
        let content = try entitiesContentSource()
        XCTAssertTrue(content.contains("store.rename(entityId:"),
                      "rename must go through EntityStore.rename (patches in place)")
    }
}
