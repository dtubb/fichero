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

    func testArtifactsPaneRoutesProvenanceClicksThroughSharedSourceNavigation() throws {
        let source = try Self.appSource("Views/Library/Inspector/ArtifactsInspectorPane.swift")
        let detailSource = try Self.appSource("Views/Library/Inspector/ArtifactDetailView.swift")

        XCTAssertTrue(source.contains("NotificationCenter.default.post("))
        XCTAssertTrue(source.contains("name: .ficheroOpenClaimSource"))
        XCTAssertTrue(detailSource.contains("LabeledContent(\"Source\")"))
    }

    func testArtifactsPaneUsesOwnOnlyArtifactScope() throws {
        let source = try Self.appSource("Views/Library/Inspector/ArtifactsInspectorPane.swift")

        XCTAssertTrue(source.contains("includeDescendants: false"))
        XCTAssertFalse(source.contains("private var includesDescendantArtifacts"))
    }

    func testEntitiesInspectorUsesSharedBottomMiniToolbar() throws {
        let inspectorSource = try Self.appSource("Views/Library/DocumentInspector/DocumentInspector.swift")
        let entitiesSource = try Self.appSource("Views/Library/DocumentInspector/DocumentInspectorArtifactsTab+EntitiesTab.swift")

        XCTAssertTrue(inspectorSource.contains("struct InspectorBottomMiniToolbar"))
        XCTAssertTrue(entitiesSource.contains("InspectorBottomMiniToolbar(statusText: entitiesToolbarStatusText)"))
    }

    func testEntitySearchRoutingUsesTypedStateInsteadOfNotificationBus() throws {
        let contentSource = try Self.appSource("Views/ContentView.swift")
        let sharedSource = try Self.appSource("Views/Library/DocumentInspector/DocumentInspectorArtifactsTab+Shared.swift")
        let entitiesSource = try Self.appSource("Views/Library/DocumentInspector/DocumentInspectorArtifactsTab+EntitiesTab.swift")

        XCTAssertTrue(sharedSource.contains("final class EntitySearchState"))
        XCTAssertTrue(contentSource.contains(".onChange(of: entitySearchState.requestID)"))
        XCTAssertTrue(entitiesSource.contains("EntitySearchState.shared.request("))
        XCTAssertFalse(sharedSource.contains("ficheroEntitySearchRequested"))
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

    func testInspectorListsUseFullRowContentShapes() throws {
        let artifactList = try Self.appSource("Views/Library/Inspector/ArtifactListView.swift")
        let annotationList = try Self.appSource("Views/Library/Inspector/AnnotationListView.swift")
        let citationList = try Self.appSource("Views/Library/Inspector/CitationListView.swift")
        let noteList = try Self.appSource("Views/Notes/NoteListView.swift")

        XCTAssertTrue(artifactList.contains(".contentShape(Rectangle())"))
        XCTAssertTrue(annotationList.contains(".contentShape(Rectangle())"))
        XCTAssertTrue(citationList.contains(".contentShape(Rectangle())"))
        XCTAssertTrue(noteList.contains(".contentShape(Rectangle())"))
    }

    func testDocumentInspectorNoLongerIncludesOutlineTabSurface() throws {
        let source = try Self.appSource("Views/Library/DocumentInspector/DocumentInspector.swift")

        XCTAssertFalse(source.contains("SourceOutlineView(documentId: doc.id)"))
        XCTAssertFalse(source.contains(".outline"))
    }
}
