@testable import Fichero
import Foundation
import XCTest

/// Tests for KGFocusState — cross-view knowledge-graph focus (entity/claim +
/// source document/page). Locks the focus transitions: focusing an entity
/// clears any focused claim, focusing a claim can co-set its entity, and clear
/// resets every field. Uses fresh instances (not the `shared` singleton) so the
/// cases stay isolated.
@MainActor
final class KGFocusStateTests: XCTestCase {

    func testFocusEntitySetsFieldsAndClearsClaim() {
        let state = KGFocusState()
        state.focusClaim(claimId: "cl-1")
        XCTAssertEqual(state.focusedClaimId, "cl-1")

        state.focusEntity(entityId: "e-1", sourceDocumentId: "d-1", sourcePageLabel: "p1")
        XCTAssertEqual(state.focusedEntityId, "e-1")
        XCTAssertNil(state.focusedClaimId, "focusing an entity must clear the claim")
        XCTAssertEqual(state.sourceDocumentId, "d-1")
        XCTAssertEqual(state.sourcePageLabel, "p1")
    }

    func testFocusClaimCanCoSetEntity() {
        let state = KGFocusState()
        state.focusClaim(claimId: "cl-2", entityId: "e-2")
        XCTAssertEqual(state.focusedClaimId, "cl-2")
        XCTAssertEqual(state.focusedEntityId, "e-2")
    }

    func testFocusEntityWithoutSourceResetsSourceFields() {
        let state = KGFocusState()
        state.focusEntity(entityId: "e", sourceDocumentId: "d", sourcePageLabel: "p")
        XCTAssertEqual(state.sourceDocumentId, "d")

        // A later focus with no source must not leave the stale source attached.
        state.focusEntity(entityId: "e2")
        XCTAssertEqual(state.focusedEntityId, "e2")
        XCTAssertNil(state.sourceDocumentId)
        XCTAssertNil(state.sourcePageLabel)
    }

    func testClearResetsEveryField() {
        let state = KGFocusState()
        state.focusEntity(entityId: "e", sourceDocumentId: "d", sourcePageLabel: "p")
        state.clear()
        XCTAssertNil(state.focusedEntityId)
        XCTAssertNil(state.focusedClaimId)
        XCTAssertNil(state.sourceDocumentId)
        XCTAssertNil(state.sourcePageLabel)
    }
}
