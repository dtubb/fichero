@testable import Fichero
import XCTest

@MainActor
final class DocumentInspectorTests: XCTestCase {
    private static func appSource(_ relativePath: String) throws -> String {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
        return try String(contentsOf: root.appendingPathComponent(relativePath), encoding: .utf8)
    }

    func testClampedSelectedTabFallsBackWhenEditsUnavailable() {
        let folder = Document(
            id: "folder-1",
            docType: .folder,
            name: "Folder",
            status: .completed
        )

        XCTAssertEqual(
            DocumentInspector.clampedSelectedTab(.edits, for: folder),
            .content
        )
    }

    func testClampedSelectedTabKeepsEditsForPageDocuments() {
        let page = Document(
            id: "page-1",
            docType: .page,
            name: "Page 1",
            status: .completed
        )

        XCTAssertEqual(
            DocumentInspector.clampedSelectedTab(.edits, for: page),
            .edits
        )
    }

    func testArtifactsPaneReloadsOnWorkflowSignals() throws {
        let source = try Self.appSource("Views/Library/Inspector/ArtifactsInspectorPane.swift")

        XCTAssertTrue(source.contains(".onChange(of: executionObserver.fileCompletedCount)"))
        XCTAssertTrue(source.contains(".onChange(of: executionObserver.workflowCompletedCount)"))
        XCTAssertTrue(source.contains("Task { await store.reload() }"))
    }

    func testFocusedEntityRoutesToEntitiesTabInsteadOfReplacingInspector() throws {
        let source = try Self.appSource("Views/Library/DocumentInspector/DocumentInspector.swift")

        XCTAssertTrue(source.contains("selectedTab = .entities"))
        XCTAssertTrue(source.contains("selectedEntityId: kgFocusState.focusedEntityId"))
        XCTAssertFalse(source.contains("Label(\"Back to document\", systemImage: \"chevron.left\")"))
    }
}
