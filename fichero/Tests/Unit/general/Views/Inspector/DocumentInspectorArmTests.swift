@testable import Fichero
import FicheroAPIClient
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

    // MARK: - #4850: cancellation is not a failure, and a real failure names its cause

    private struct FetchFailure: LocalizedError {
        var errorDescription: String? { "server said no" }
    }

    func testASuccessfulFetchIsLoaded() async {
        let entity = Components.Schemas.KnowledgeEntity(canonicalName: "Ana")
        let outcome = await EntityArmLoad.run(entityId: "e1", libraryPath: "/lib.fichero") { entity }
        guard case .loaded(let loaded) = outcome else { return XCTFail("expected .loaded, got \(outcome)") }
        XCTAssertEqual(loaded.canonicalName, "Ana")
    }

    func testARealFailureNamesTheLibraryAndTheCause() async {
        let outcome = await EntityArmLoad.run(entityId: "e1", libraryPath: "/lib.fichero") { throw FetchFailure() }
        guard case .failed(let reason) = outcome else { return XCTFail("expected .failed, got \(outcome)") }
        XCTAssertTrue(reason.contains("/lib.fichero"), "a cross-library mismatch must be visible: \(reason)")
        XCTAssertTrue(reason.contains("server said no"), reason)
    }

    /// A fetch superseded by a focus change (or a torn-down arm) must never show as an error.
    func testACancelledFetchIsSupersededNotFailed() async {
        let task = Task {
            await EntityArmLoad.run(entityId: "e1", libraryPath: "/lib.fichero") {
                try await Task.sleep(nanoseconds: 60_000_000_000)
                throw FetchFailure()
            }
        }
        task.cancel()
        let outcome = await task.value
        guard case .superseded = outcome else { return XCTFail("expected .superseded, got \(outcome)") }
    }
}
