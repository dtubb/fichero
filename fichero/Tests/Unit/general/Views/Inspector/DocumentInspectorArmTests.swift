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

    // MARK: - #4850: cancellation is not a failure, and a real failure names its cause

    /// `EntityInspectorArm` is a private nested struct with no seam to mount
    /// and cancel a real `.task` from outside this file — source-scan, the
    /// same limitation this codebase's other SwiftUI-async views accept
    /// elsewhere (e.g. `ChatViewBoundaryTests`). Pins that a cancelled fetch
    /// (the focused entity changed again before this one returned) never
    /// reaches `loadFailed = true`.
    func testEntityInspectorArmGuardsCancellationBeforeMarkingFailure() throws {
        let source = try AppSource.code("Views/Inspector/Document/DocumentInspector.swift")
        guard let taskStart = source.range(of: ".task(id: entityId) {"),
              let catchStart = source.range(of: "} catch {", range: taskStart.upperBound..<source.endIndex),
              let taskEnd = source.range(of: "\n            }", range: catchStart.upperBound..<source.endIndex)
        else {
            XCTFail("could not locate EntityInspectorArm's .task(id: entityId) catch block")
            return
        }
        let catchBody = source[catchStart.upperBound..<taskEnd.lowerBound]
        XCTAssertTrue(
            catchBody.contains("guard !Task.isCancelled else { return }"),
            "a cancelled fetch must never be shown as a failure"
        )
        XCTAssertTrue(
            catchBody.contains("entityInspectorArmLogger.error("),
            "a real failure must be logged with a typed error, not silently discarded"
        )
        XCTAssertTrue(
            catchBody.contains("libraryPath"),
            "the failure reason must name which library the request used, so a cross-library mismatch is visible, not just 'Entity Unavailable'"
        )
    }
}
