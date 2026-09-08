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

    func testCreatedEntityForcesLibraryReloadSoTheRowAppears() throws {
        let source = try entitiesContentSource()
        // The change-stream's scheduleReload targets the document scope; the table reads
        // the library-wide list, so a manual create MUST force a library-wide reload or
        // the new row never appears here.
        XCTAssertTrue(source.contains("loadEntities(limit: 25000, force: true)"),
                      "a manual create must force-reload the library-wide entity list")
    }
}
