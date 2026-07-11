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

        XCTAssertTrue(source.contains("ClaimSourceNavigationState.shared.request("))
        XCTAssertTrue(source.contains("ClaimSourceNavigationRequest("))
        XCTAssertTrue(detailSource.contains("LabeledContent(\"Source\")"))
    }

    func testArtifactsPaneUsesOwnOnlyArtifactScope() throws {
        let source = try Self.appSource("Views/Library/Inspector/ArtifactsInspectorPane.swift")

        XCTAssertTrue(source.contains("includeDescendants: false"))
        XCTAssertFalse(source.contains("private var includesDescendantArtifacts"))
    }

    func testArtifactsTranslateActionLivesInInspectorMiniToolbar() throws {
        let source = try Self.appSource("Views/Library/Inspector/ArtifactsInspectorPane.swift")
        let listSource = try Self.appSource("Views/Library/Inspector/ArtifactListView.swift")

        XCTAssertTrue(source.contains("InspectorBottomMiniToolbar(statusText: artifactsToolbarStatusText)"))
        XCTAssertTrue(source.contains("translateMenu"))
        XCTAssertFalse(source.contains("ToolbarItem(placement: .automatic) {\n                translateMenu"))
        XCTAssertTrue(listSource.contains("case \"translation\":"))
        XCTAssertTrue(listSource.contains("return \"Translated\""))
    }

    func testInspectorListPanesUseSharedBottomMiniToolbar() throws {
        let inspectorSource = try Self.appSource("Views/Library/DocumentInspector/DocumentInspector.swift")
        let entitiesSource = try Self.appSource("Views/Library/DocumentInspector/DocumentInspectorArtifactsTab+EntitiesTab.swift")
        let artifactsSource = try Self.appSource("Views/Library/Inspector/ArtifactsInspectorPane.swift")
        let citationsSource = try Self.appSource("Views/Library/Inspector/CitationsInspectorPane.swift")
        let annotationsSource = try Self.appSource("Views/Library/Inspector/AnnotationsInspectorPane.swift")
        let notesSource = try Self.appSource("Views/Notes/NotesInspectorPane.swift")

        XCTAssertTrue(inspectorSource.contains("struct InspectorBottomMiniToolbar"))
        XCTAssertTrue(entitiesSource.contains("InspectorBottomMiniToolbar(statusText: entitiesToolbarStatusText)"))
        XCTAssertTrue(artifactsSource.contains("InspectorBottomMiniToolbar(statusText: artifactsToolbarStatusText)"))
        XCTAssertTrue(citationsSource.contains("InspectorBottomMiniToolbar(statusText: citationsToolbarStatusText)"))
        XCTAssertTrue(annotationsSource.contains("InspectorBottomMiniToolbar(statusText: annotationsToolbarStatusText)"))
        XCTAssertTrue(notesSource.contains("InspectorBottomMiniToolbar(statusText: notesToolbarStatusText)"))
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

    func testClaimSourceRoutingUsesTypedStateInsteadOfNotificationBus() throws {
        let contentSource = try Self.appSource("Views/ContentView.swift")
        let sharedSource = try Self.appSource("Views/Library/DocumentInspector/DocumentInspectorArtifactsTab+Shared.swift")
        let artifactsSource = try Self.appSource("Views/Library/Inspector/ArtifactsInspectorPane.swift")
        let searchSource = try Self.appSource("Views/Search/SearchView+Helpers.swift")

        XCTAssertTrue(sharedSource.contains("final class ClaimSourceNavigationState"))
        XCTAssertTrue(contentSource.contains(".onChange(of: claimSourceNavigationState.requestID)"))
        XCTAssertTrue(artifactsSource.contains("ClaimSourceNavigationState.shared.request("))
        XCTAssertTrue(searchSource.contains("ClaimSourceNavigationState.shared.request(request)"))
        XCTAssertFalse(contentSource.contains(".ficheroOpenClaimSource"))
        XCTAssertFalse(sharedSource.contains("static let ficheroOpenClaimSource"))
    }

    func testEntityListNameUsesSearchClickWithDoubleClickRename() throws {
        let entitiesSource = try Self.appSource("Views/Library/DocumentInspector/DocumentInspectorArtifactsTab+EntitiesTab.swift")

        XCTAssertTrue(entitiesSource.contains("Button {"))
        XCTAssertTrue(entitiesSource.contains("postSearch("))
        XCTAssertTrue(entitiesSource.contains("Search the library for"))
        XCTAssertTrue(entitiesSource.contains(".simultaneousGesture("))
        XCTAssertTrue(entitiesSource.contains("TapGesture(count: 2).onEnded { beginRename(entity) }"))
    }

    func testLegacyCitationInfoPanelsUseEnvironmentStores() throws {
        let citationsSource = try Self.appSource("Views/Library/DocumentInspector/DocumentInspectorInfoTab+Citations.swift")
        let bibliographySource = try Self.appSource("Views/Library/DocumentInspector/DocumentInspectorInfoTab+Bibliography.swift")
        let interpretationsSource = try Self.appSource(
            "Views/Library/DocumentInspector/DocumentInspectorArtifactsTab+Interpretations.swift"
        )
        let interpretationsTabSource = try Self.appSource(
            "Views/Library/DocumentInspector/DocumentInterpretationsTab.swift"
        )
        let interpretationStoreSource = try Self.appSource("Models/InterpretationStore.swift")
        let serviceSource = try Self.appSource("Services/ArtifactServiceGenerated.swift")

        XCTAssertTrue(citationsSource.contains("@Environment(CitationStore.self)"))
        XCTAssertFalse(citationsSource.contains("LibraryManager.shared.globalLibrary?.citationStore"))
        XCTAssertTrue(bibliographySource.contains("@Environment(ReferenceStore.self)"))
        XCTAssertFalse(bibliographySource.contains("LibraryManager.shared.globalLibrary?.referenceStore"))
        XCTAssertTrue(interpretationsSource.contains("@Environment(InterpretationStore.self)"))
        XCTAssertFalse(interpretationsSource.contains("LibraryManager.shared.globalLibrary?.interpretationStore"))
        XCTAssertTrue(interpretationsSource.contains("try await store.create("))
        XCTAssertTrue(interpretationsSource.contains("try await store.update("))
        XCTAssertFalse(interpretationsSource.contains("entityService."))
        XCTAssertFalse(interpretationsTabSource.contains("EntityServiceGenerated"))
        XCTAssertTrue(interpretationStoreSource.contains("func loadFrameworks() async"))
        XCTAssertTrue(serviceSource.contains("client.api.listInterpretationsApiHermeneuticsInterpretationsGet"))
        XCTAssertTrue(serviceSource.contains("client.api.createInterpretationApiHermeneuticsInterpretationsPost"))
        XCTAssertFalse(serviceSource.contains("endpointData(path: \"/api/kg/interpretations"))
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
        let inspectorSource = try Self.appSource("Views/Library/DocumentInspector/DocumentInspector.swift")
        let artifactList = try Self.appSource("Views/Library/Inspector/ArtifactListView.swift")
        let annotationList = try Self.appSource("Views/Library/Inspector/AnnotationListView.swift")
        let citationList = try Self.appSource("Views/Library/Inspector/CitationListView.swift")
        let noteList = try Self.appSource("Views/Notes/NoteListView.swift")
        let entitiesSource = try Self.appSource("Views/Library/DocumentInspector/DocumentInspectorArtifactsTab+EntitiesTab.swift")

        XCTAssertTrue(inspectorSource.contains("func inspectorListRowTarget()"))
        XCTAssertTrue(artifactList.contains(".inspectorListRowTarget()"))
        XCTAssertTrue(annotationList.contains(".inspectorListRowTarget()"))
        XCTAssertTrue(citationList.contains(".inspectorListRowTarget()"))
        XCTAssertTrue(noteList.contains(".inspectorListRowTarget()"))
        XCTAssertTrue(entitiesSource.contains(".inspectorListRowTarget()"))
    }

    func testDocumentInspectorNoLongerIncludesOutlineTabSurface() throws {
        let source = try Self.appSource("Views/Library/DocumentInspector/DocumentInspector.swift")

        XCTAssertFalse(source.contains("SourceOutlineView(documentId: doc.id)"))
        XCTAssertFalse(source.contains(".outline"))
    }
}
