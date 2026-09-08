@testable import Fichero
import XCTest

/// spec: kg-entity-inspector — `kg.entity.select.inspector-shows-entity` (F2).
///
/// The inspector must show a FOCUSED ENTITY even when no document is selected
/// (the Entities collection / Knowledge Graph mode focus an entity, not a file),
/// instead of falling to "No selection". The which-arm rule is a pure decision,
/// pinned here without a rendered view; a document still wins when present
/// (`kg.entity.select.routes-to-entities-tab` keeps the entity in that doc's tab).
final class DocumentInspectorArmTests: XCTestCase {

    func testDocumentWinsWhenPresent() {
        XCTAssertEqual(
            DocumentInspector.inspectorArm(hasDocument: true, focusedEntityId: nil),
            .document
        )
        XCTAssertEqual(
            DocumentInspector.inspectorArm(hasDocument: true, focusedEntityId: "e1"),
            .document,
            "a shown document keeps the inspector; the entity routes to its Entities tab"
        )
    }

    func testEntityArmWhenNoDocumentButEntityFocused() {
        XCTAssertEqual(
            DocumentInspector.inspectorArm(hasDocument: false, focusedEntityId: "e1"),
            .entity,
            "no document + a focused entity must show the entity, never 'No selection'"
        )
    }

    func testEmptyWhenNothing() {
        XCTAssertEqual(
            DocumentInspector.inspectorArm(hasDocument: false, focusedEntityId: nil),
            .empty
        )
    }
}
