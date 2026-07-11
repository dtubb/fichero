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

    func testEntityNotesAndAnnotationsUseLowerDetailPanes() throws {
        let entitiesSource = try Self.appSource("Views/Library/DocumentInspector/DocumentInspectorArtifactsTab+EntitiesTab.swift")
        let notesSource = try Self.appSource("Views/Notes/NotesInspectorPane.swift")
        let annotationsSource = try Self.appSource("Views/Library/Inspector/AnnotationsInspectorPane.swift")

        XCTAssertTrue(entitiesSource.contains("PlatformVSplitView"))
        XCTAssertTrue(notesSource.contains("PlatformVSplitView"))
        XCTAssertTrue(annotationsSource.contains("PlatformVSplitView"))
        XCTAssertFalse(entitiesSource.localizedCaseInsensitiveContains("back to document"))
        XCTAssertFalse(notesSource.localizedCaseInsensitiveContains("back to document"))
        XCTAssertFalse(annotationsSource.localizedCaseInsensitiveContains("back to document"))
    }

    func testArtifactInspectorListSupportsDoubleClickOpenInWindow() throws {
        let source = try Self.appSource("Views/Library/Inspector/ArtifactListView.swift")

        XCTAssertTrue(source.contains(".onTapGesture(count: 2)"))
        XCTAssertTrue(source.contains("focused.select(artifact.id, in: store.items)"))
        XCTAssertTrue(source.contains("onOpenInWindow()"))
    }

    func testOutlineArtifactDoubleClickOpensArtifactWindowInsteadOfParentDocument() throws {
        let source = try Self.appSource("Views/Library/LibraryView+TableMapViews.swift")

        XCTAssertTrue(source.contains("handleOutlineDoubleClickSelection()"))
        XCTAssertTrue(source.contains("if let artifactSelection = artifactSelectionForNodeId(firstId)"))
        XCTAssertTrue(source.contains("openWindow(id: \"artifact-detail\")"))
    }

    func testDocumentInspectorNoLongerIncludesOutlineTabSurface() throws {
        let source = try Self.appSource("Views/Library/DocumentInspector/DocumentInspector.swift")

        XCTAssertFalse(source.contains("SourceOutlineView(documentId: doc.id)"))
        XCTAssertFalse(source.contains(".outline"))
    }
}
