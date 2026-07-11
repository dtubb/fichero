@testable import Fichero
import FicheroAPIClient
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

    // MARK: - Multi-level undo walk (#3444)

    private func auditEntry(
        _ id: String,
        undone: Bool = false,
        inverseOf: String? = nil,
        undoable: Bool = true
    ) -> Components.Schemas.AuditLogEntry {
        Components.Schemas.AuditLogEntry(
            id: id,
            actionName: "entity.merge",
            actor: "human",
            targetIds: [],
            createdAt: "t",
            undone: undone,
            inverseOf: inverseOf,
            undoable: undoable
        )
    }

    func testNextUndoableWalksToMostRecentForwardUndoableAction() {
        // Newest-first: an inverse (redo target), an already-undone action, then
        // two live forward actions. The walk targets the newest live forward one.
        let entries = [
            auditEntry("inv", inverseOf: "c"),   // skip — an inverse/redo row
            auditEntry("c", undone: true),        // skip — already undone
            auditEntry("b"),                      // <- next undo target
            auditEntry("a")
        ]
        XCTAssertEqual(AuditStore.nextUndoable(in: entries)?.id, "b")
    }

    func testNextUndoableSkipsNonUndoableRows() {
        let entries = [auditEntry("x", undoable: false), auditEntry("y")]
        XCTAssertEqual(AuditStore.nextUndoable(in: entries)?.id, "y")
    }

    func testNextUndoableNilWhenNothingReversible() {
        XCTAssertNil(AuditStore.nextUndoable(in: []))
        XCTAssertNil(AuditStore.nextUndoable(in: [auditEntry("z", undone: true)]))
    }

    // MARK: - Switcher section mapping (#3457)

    func testSwitcherMapsEachTabToItsSection() {
        // doc = nil → all tabs available, so this is the pure section mapping the
        // top-icon-row switcher uses (no doc-type clamping).
        XCTAssertEqual(DocumentInspector.section(for: .content, in: nil), .source)
        XCTAssertEqual(DocumentInspector.section(for: .info, in: nil), .source)
        XCTAssertEqual(DocumentInspector.section(for: .artifacts, in: nil), .artifacts)
        XCTAssertEqual(DocumentInspector.section(for: .entities, in: nil), .knowledge)
        XCTAssertEqual(DocumentInspector.section(for: .knowledgeGraph, in: nil), .knowledge)
        XCTAssertEqual(DocumentInspector.section(for: .citations, in: nil), .knowledge)
        XCTAssertEqual(DocumentInspector.section(for: .notes, in: nil), .notes)
        XCTAssertEqual(DocumentInspector.section(for: .annotations, in: nil), .notes)
        XCTAssertEqual(DocumentInspector.section(for: .interpretations, in: nil), .notes)
    }

    func testSwitcherFallsBackToSourceForEdits() {
        // Edits left the inspector (#3434), so it maps to no section and the
        // switcher clamps to Source rather than showing a dead segment.
        XCTAssertEqual(DocumentInspector.section(for: .edits, in: nil), .source)
    }

    // MARK: - Source outline tree fold (#3440)

    private func outlineRow(_ id: String, depth: Int) -> Components.Schemas.DocumentOutlineRow {
        Components.Schemas.DocumentOutlineRow(id: id, depth: depth, kind: "section", label: id, count: 0)
    }

    func testSourceOutlineTreeFoldsFlatDepthRowsIntoHierarchy() {
        // Flat depth-first rows: doc(0) → [ pageA(1) → [ chunk(2) ], pageB(1) ].
        let rows = [
            outlineRow("doc", depth: 0),
            outlineRow("pageA", depth: 1),
            outlineRow("chunk", depth: 2),
            outlineRow("pageB", depth: 1)
        ]
        let tree = SourceOutlineNode.tree(from: rows)

        XCTAssertEqual(tree.map(\.id), ["doc"])
        XCTAssertEqual(tree.first?.children?.map(\.id), ["pageA", "pageB"])
        XCTAssertEqual(tree.first?.children?.first?.children?.map(\.id), ["chunk"])
        // A leaf has nil children (so the outline shows no empty disclosure).
        XCTAssertNil(tree.first?.children?.last?.children)
    }

    func testSourceOutlineTreeEmptyForNoRows() {
        XCTAssertTrue(SourceOutlineNode.tree(from: []).isEmpty)
    }

    // MARK: - Source outline reveal anchor (#3440 + #3441)

    func testOutlineNavigationRequestForRevealCapableRow() {
        let row = Components.Schemas.DocumentOutlineRow(
            id: "p1",
            depth: 1,
            kind: "page",
            label: "Page 1",
            count: 0,
            sourceDocumentId: "doc-9",
            pageLabel: "p. 1",
            sourceCapability: "reveal"
        )
        let request = SourceOutlineNode.navigationRequest(for: row)
        XCTAssertEqual(request?.documentId, "doc-9")
        XCTAssertEqual(request?.pageLabel, "p. 1")
    }

    func testOutlineNavigationRequestNilForGroupOrAnchorlessRow() {
        // Group/structural row without a source anchor must NOT fake one.
        let group = Components.Schemas.DocumentOutlineRow(
            id: "g", depth: 0, kind: "entities", label: "Entities", count: 5
        )
        XCTAssertNil(SourceOutlineNode.navigationRequest(for: group))
        // Reveal capability but no document id → still nil.
        let noDoc = Components.Schemas.DocumentOutlineRow(
            id: "x", depth: 1, kind: "page", label: "P", count: 0, sourceCapability: "reveal"
        )
        XCTAssertNil(SourceOutlineNode.navigationRequest(for: noDoc))
    }

    // MARK: - Interpretation inspector on the injected store (#3429)

    func testInterpretationSectionUsesInjectedStoreNotGlobalLibrary() throws {
        let source = try Self.appSource(
            "Views/Library/DocumentInspector/DocumentInspectorArtifactsTab+Interpretations.swift"
        )

        // #3429: the interpretation inspector reads InterpretationStore from the
        // environment and drives scope + create/edit through it — never the
        // LibraryManager.shared globalLibrary singleton. This guard fails if the
        // singleton reach-through is ever reintroduced.
        XCTAssertTrue(source.contains("@Environment(InterpretationStore.self)"))
        XCTAssertTrue(source.contains("store.setScope(documentId:"))
        XCTAssertTrue(source.contains("store.create("))
        XCTAssertFalse(source.contains("LibraryManager.shared"))
        XCTAssertFalse(source.contains("globalLibrary"))
    }

    // MARK: - Content-tab artifacts on the store (#3427)

    func testDisplayAttributesStripObservesArtifactStoreNotService() throws {
        let source = try Self.appSource("Views/Library/DisplayAttributesStrip.swift")

        // The content-tab strip reads the shared ArtifactStore, not a view-local
        // ArtifactServiceGenerated fetch (#3427).
        XCTAssertTrue(source.contains("@Environment(ArtifactStore.self)"))
        XCTAssertTrue(source.contains("artifactStore.items"))
        XCTAssertTrue(source.contains("artifactStore.setScope("))
        XCTAssertFalse(source.contains("@Environment(ArtifactServiceGenerated.self)"))
        XCTAssertFalse(source.contains("artifactService.getArtifacts"))
    }
}
