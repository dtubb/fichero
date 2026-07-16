@testable import Fichero
import FicheroAPIClient
import Foundation
import XCTest

// swiftlint:disable file_length
// Tests for DocumentStoreTypes (request DTOs + error model) and
// SidebarViewTypes (AppViewMode category routing + ActivityChildType
// label/icon table + SelectedActivityRun.with helper).
// swiftlint:disable:next type_body_length
final class DocumentStoreAndSidebarTypesTests: XCTestCase {

    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    // Note: DocumentCreateRequest / DocumentUpdateRequest were removed in #3030
    // (create/update now go through DocumentServiceGenerated →
    // Components.Schemas.DocumentCreate/DocumentUpdate). Their snake_case
    // encoding is now the generated client's contract, exercised via the
    // generated-op request tests in DocumentListMigrationTests.

    // MARK: - DocumentHierarchy

    func testHierarchyParentIsLastAncestor() {
        let root = makeDoc(id: "root", name: "Root")
        let mid = makeDoc(id: "mid", name: "Mid")
        let leaf = makeDoc(id: "leaf", name: "Leaf")
        let hierarchy = DocumentHierarchy(ancestors: [root, mid], document: leaf, children: [])
        XCTAssertEqual(hierarchy.parent?.id, "mid")
    }

    func testHierarchyParentNilForRoot() {
        let root = makeDoc(id: "root", name: "Root")
        let hierarchy = DocumentHierarchy(ancestors: [], document: root, children: [])
        XCTAssertNil(hierarchy.parent)
    }

    func testHierarchyBreadcrumbAppendsDocument() {
        let root = makeDoc(id: "root", name: "Root")
        let leaf = makeDoc(id: "leaf", name: "Leaf")
        let hierarchy = DocumentHierarchy(ancestors: [root], document: leaf, children: [])
        XCTAssertEqual(hierarchy.breadcrumb.map(\.id), ["root", "leaf"])
    }

    // `testDocumentStoreErrorDescriptions` was deleted with `DocumentStoreError`
    // itself (#3919): its only thrower, `DocumentStore.importFile(at:)`, had no
    // callers, so the enum was unthrowable and the test only proved that dead
    // strings still read correctly.

    func testDocumentStoreLoadsSidebarRootsThroughGeneratedService() throws {
        let source = try Self.appSource("Models/DocumentStore.swift")

        XCTAssertTrue(source.contains("documentService.getRoots()"))
        XCTAssertFalse(source.contains("api.get(\"/documents\""))
        XCTAssertFalse(source.contains("api.post(\"/documents\""))
    }

    // MARK: - Batch library-item column metadata (#3758)

    /// Test seam: a DocumentStore whose generated client is bound to a stubbed
    /// URLProtocol session, so `libraryItemColumns` exercises the real
    /// request/response mapping without a live engine.
    private static func makeStubbedStore() -> DocumentStore {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [ColumnsStubURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let client = FicheroClient(
            baseURL: URL(string: "https://test.fichero")!,
            libraryPath: "/tmp/test.fichero",
            session: session
        )
        return DocumentStore(apiClient: APIClient(client: client))
    }

    func testLibraryItemColumnsReturnsRowsFromBackendThroughTheStore() async throws {
        // The store is the only endpoint accessor: it POSTs the item ids and
        // returns the parsed per-item rows.
        ColumnsStubURLProtocol.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.path, "/api/library-items/columns")
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, Data(#"{"items":[{"item_id":"a"},{"item_id":"b"}]}"#.utf8))
        }
        defer { ColumnsStubURLProtocol.handler = nil }

        let store = Self.makeStubbedStore()
        let rows = try await store.libraryItemColumns(itemIds: ["a", "b"])

        XCTAssertEqual(rows.map(\.itemId), ["a", "b"])
    }

    func testLibraryItemColumnsShortCircuitsOnEmptyInputWithoutHittingTheNetwork() async throws {
        // Empty input must not reach the backend (it would just echo an empty
        // set anyway) — the store returns [] directly.
        ColumnsStubURLProtocol.handler = { request in
            XCTFail("empty item ids must not hit the network")
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (response, Data(#"{"items":[]}"#.utf8))
        }
        defer { ColumnsStubURLProtocol.handler = nil }

        let store = Self.makeStubbedStore()
        let rows = try await store.libraryItemColumns(itemIds: [])

        XCTAssertTrue(rows.isEmpty)
    }

    // MARK: - AppViewMode.category

    func testAppViewModeCategoryRouting() {
        // Locks the sidebar-to-toolbar wire: each AppViewMode collapses
        // into an ItemCategory used to decide which toolbar set renders.
        XCTAssertEqual(AppViewMode.library(nil).category, .folder)
        XCTAssertEqual(AppViewMode.search(nil).category, .search)
        XCTAssertEqual(AppViewMode.chat(nil).category, .chat)
        XCTAssertEqual(AppViewMode.comparison(nil).category, .chat)
        XCTAssertEqual(AppViewMode.workflow(nil).category, .workflow)
        XCTAssertEqual(AppViewMode.chain(nil).category, .workflow)
        XCTAssertEqual(AppViewMode.batches.category, .workflow)
        XCTAssertEqual(AppViewMode.batch(nil).category, .workflow)
        XCTAssertEqual(AppViewMode.automation.category, .workflow)
        XCTAssertEqual(AppViewMode.schedule(nil).category, .workflow)
        XCTAssertEqual(AppViewMode.trigger(nil).category, .workflow)
        XCTAssertEqual(AppViewMode.activity(nil).category, .workflow)
    }

    func testEntitiesSidebarEntryPointRoutesToLibraryList() throws {
        let source = try Self.appSource("Views/Sidebar/SidebarView.swift")

        XCTAssertTrue(source.contains("id == \"entities-browser\""))
        XCTAssertTrue(source.contains("sidebarMode = .library"))
        XCTAssertTrue(source.contains("viewMode = .library(nil)"))
    }

    func testEntitiesSidebarEntryPointIsPinnedAndFeatureGated() throws {
        let source = try Self.appSource("Views/Sidebar/SidebarView+PinnedNavigationRows.swift")

        XCTAssertTrue(source.contains("tag: \"entities-browser\""))
        XCTAssertTrue(source.contains("systemImage: SidebarMode.knowledgeGraph.icon"))
        XCTAssertTrue(source.contains("FeatureManager.shared.isKnowledgeGraphEnabled"))
        XCTAssertTrue(source.contains("entitiesNavigationRow()"))
    }

    func testEntityLibrarySelectionLocksDisplayModeToList() throws {
        let stateSource = try Self.appSource("Views/ContentView+State.swift")

        XCTAssertTrue(stateSource.contains("var isEntityLibrarySelection: Bool"))
        XCTAssertTrue(stateSource.contains("if isEntityLibrarySelection {"))
        XCTAssertTrue(stateSource.contains("return [.list]"))
        XCTAssertTrue(stateSource.contains("if newFolderId == \"entities-browser\""))
        XCTAssertTrue(stateSource.contains("viewDisplayMode = .list"))
    }

    func testEntityLibrarySelectionRoutesBrowserSelectionIntoKGFocus() throws {
        let stateSource = try Self.appSource("Views/ContentView+State.swift")
        let navigationSource = try Self.appSource("Views/ContentView+Navigation.swift")

        XCTAssertTrue(stateSource.contains("if isEntityLibrarySelection {"))
        XCTAssertTrue(stateSource.contains("kgFocusState.focusEntity(entityId: firstId)"))
        XCTAssertTrue(stateSource.contains("kgFocusState.clear()"))
        XCTAssertTrue(navigationSource.contains("contentCollection: isEntityLibrarySelection ? .entities : .documents"))
    }

    func testSidebarPinnedRowsExposeMindPalaceResearchAndComparison() throws {
        let source = try Self.appSource("Views/Sidebar/SidebarView+PinnedNavigationRows.swift")

        XCTAssertTrue(source.contains("tag: \"comparison-browser\""))
        XCTAssertTrue(source.contains("if FeatureManager.shared.isChatEnabled {"))
        XCTAssertFalse(source.contains("if FeatureManager.shared.isWorkflowsEnabled {\n            comparisonNavigationRow()"))
        XCTAssertTrue(source.contains("tag: \"research-browser\""))
        XCTAssertTrue(source.contains("FeatureManager.shared.isResearchEnabled"))
    }

    func testPinnedSidebarEntryPointsRouteToExpectedSurfaces() throws {
        let source = try Self.appSource("Views/Sidebar/SidebarView.swift")

        XCTAssertTrue(source.contains("id == \"comparison-browser\""))
        XCTAssertTrue(source.contains("viewMode = .comparison(nil)"))
        XCTAssertTrue(source.contains("id == \"research-browser\""))
        XCTAssertTrue(source.contains("sidebarMode = .research"))
    }

    func testSidebarDisclosureRowsDisableNestedInsertionAnimation() throws {
        let source = try Self.appSource("Views/Sidebar/SidebarView+UnifiedLibrarySections.swift")

        XCTAssertTrue(source.contains(".transaction { transaction in"))
        XCTAssertTrue(source.contains("transaction.animation = nil"))
        XCTAssertTrue(source.contains("wrong lateral origin"))
    }

    func testDeferredDisclosureContentNeededForExpandableLazyFolder() {
        let folder = makeDoc(id: "folder-1", name: "Folder", childCount: 2)
        let item = SidebarItem.fromDocument(folder, libraryId: UUID())

        XCTAssertTrue(item.isExpandable)
        XCTAssertTrue(sidebarNeedsDeferredDisclosureContent(item))
    }

    func testDeferredDisclosureContentNotNeededAfterChildrenLoad() {
        let folder = makeDoc(id: "folder-1", name: "Folder", childCount: 2)
        let child = SidebarItem.folder(name: "Child", folderPath: "/child", category: .folder, libraryId: UUID())
        let item = SidebarItem.fromDocument(folder, libraryId: UUID(), children: [child])

        XCTAssertFalse(sidebarNeedsDeferredDisclosureContent(item))
    }

    func testSidebarBuilderKeepsUnloadedFolderExpandableFromChildCount() {
        let folder = makeDoc(id: "folder-1", name: "Folder", childCount: 1)
        let result = SidebarItemBuilder.buildLibraryHierarchy(from: [folder], libraryId: UUID())

        XCTAssertEqual(result.count, 1)
        XCTAssertNil(result[0].children)
        XCTAssertTrue(result[0].isExpandable)
        XCTAssertTrue(sidebarNeedsDeferredDisclosureContent(result[0]))
    }

    func testSidebarBuilderKeepsUnloadedPdfExpandableFromChildCount() {
        let pdf = Document(
            id: "pdf-1",
            parentId: nil,
            docType: .file,
            fileType: .pdf,
            name: "paper.pdf",
            path: nil,
            sequence: nil,
            bbox: nil,
            status: .completed,
            metadata: [:],
            pageContent: nil,
            childCount: 3,
            createdAt: Date(),
            updatedAt: Date()
        )
        let result = SidebarItemBuilder.buildLibraryHierarchy(from: [pdf], libraryId: UUID())

        XCTAssertEqual(result.count, 1)
        XCTAssertNil(result[0].children)
        XCTAssertTrue(result[0].isExpandable)
        XCTAssertTrue(sidebarNeedsDeferredDisclosureContent(result[0]))
    }

    func testLibraryViewClipsItsOwnPaneBounds() throws {
        let source = try Self.appSource("Views/ContentView+Navigation.swift")

        XCTAssertTrue(source.contains("Keep the library surface inside the content column"))
        XCTAssertTrue(source.contains(".clipped()"))
        XCTAssertTrue(source.contains("under the shell sidebar or off the left window edge"))
    }

    func testDetailShellColumnClipsAllPreviewLayoutsToItsBounds() throws {
        let source = try Self.appSource("Views/ContentView+ViewBuilders.swift")

        XCTAssertTrue(source.contains("Keep every library/preview/reader combination inside the detail"))
        XCTAssertTrue(source.contains("column bounds. Without this outer clip"))
        XCTAssertTrue(source.contains(".background(Color(platformColor: .textBackgroundColor))\n        .clipped()"))
    }

    func testLibraryWorkspaceDefersLiveUpdateStreamsUntilBackendReady() throws {
        let source = try Self.appSource("Views/Library/Workspace/LibraryWorkspaceRoot.swift")

        XCTAssertTrue(source.contains("@Environment(AppState.self) private var appState"))
        XCTAssertTrue(source.contains("guard appState.isBackendRunning else { return }"))
        XCTAssertTrue(source.contains("app is still probing the engine can falsely trip the paused"))
        XCTAssertTrue(source.contains("library.changeStream.start()"))
        XCTAssertTrue(source.contains("library.activityStore.start()"))
    }

    func testCurrentChatScopePrefersSelectionThenDetailThenVisibleCollection() {
        let folder = Document(id: "folder-1", docType: .folder, name: "Folder")
        let page = Document(id: "page-1", parentId: "folder-1", docType: .page, fileType: .pdf, name: "Page 1")
        let image = Document(id: "image-1", parentId: "folder-1", docType: .file, fileType: .image, name: "Image 1")

        XCTAssertEqual(
            ChatScopeBuilder.currentScopeDocumentIds(
                browserSelection: ["page-1"],
                currentDocuments: [folder, page, image],
                detailDocument: folder
            ),
            ["page-1"]
        )

        XCTAssertEqual(
            ChatScopeBuilder.currentScopeDocumentIds(
                browserSelection: [],
                currentDocuments: [folder],
                detailDocument: image
            ),
            ["image-1"]
        )

        XCTAssertEqual(
            ChatScopeBuilder.currentScopeDocumentIds(
                browserSelection: [],
                currentDocuments: [folder, page, image],
                detailDocument: folder
            ),
            ["page-1", "image-1"]
        )
    }

    func testLibraryBrowserToggleCopyUsesExplicitLibraryName() throws {
        let toolbarSource = try Self.appSource("Views/ContentView.swift")
        let menuSource = try Self.appSource("Views/Menu/ViewMenuCommands.swift")

        XCTAssertTrue(toolbarSource.contains("ToolbarItem(placement: .principal)"))
        XCTAssertTrue(toolbarSource.contains("LibraryManager.shared.getLibrary(id: windowState.libraryId)?.displayName"))
        XCTAssertTrue(toolbarSource.contains("Text(libraryName)"))
        XCTAssertTrue(menuSource.contains("Show Library Browser"))
        XCTAssertTrue(menuSource.contains("Hide Library Browser"))
        XCTAssertTrue(menuSource.contains("icon: \"books.vertical\""))
    }

    func testIpadViewMenuUsesSharedViewCommands() throws {
        let contentSource = try Self.appSource("Views/ContentView.swift")

        XCTAssertTrue(contentSource.contains("ViewMenuCommands()"))
        XCTAssertTrue(contentSource.contains("Label(\"View\", systemImage: \"rectangle.split.3x1\")"))
    }

    func testMacLaunchResyncsBackendStateAfterEngineStartup() throws {
        let appSource = try Self.appSource("FicheroApp.swift")
        let appStateSource = try Self.appSource("App/AppState.swift")

        guard
            let startRange = appSource.range(of: "try await backendService.start()"),
            let resyncRange = appSource.range(
                of: "await appState.checkBackendHealth()",
                range: startRange.upperBound..<appSource.endIndex
            ),
            let heartbeatRange = appSource.range(
                of: "appState.startBackendHeartbeat()",
                range: resyncRange.upperBound..<appSource.endIndex
            ),
            let readyRange = appSource.range(
                of: "await libraryManager.backendDidBecomeReady()",
                range: heartbeatRange.upperBound..<appSource.endIndex
            )
        else {
            return XCTFail("launch sequence changed unexpectedly")
        }

        XCTAssertLessThan(startRange.lowerBound, resyncRange.lowerBound)
        XCTAssertLessThan(resyncRange.lowerBound, heartbeatRange.lowerBound)
        XCTAssertLessThan(heartbeatRange.lowerBound, readyRange.lowerBound)
        XCTAssertFalse(appStateSource.contains("await checkBackendHealth()"))
    }

    func testBackendRetryRunsSameReadinessSideEffectsAsStartup() throws {
        let tabSource = try Self.appSource("Views/DocumentTabView.swift")
        let connectionSource = try Self.appSource("Views/Components/BackendConnectionView.swift")

        XCTAssertTrue(tabSource.contains("BackendConnectionView(appState: appState, onConnected: completeBackendRetryReadiness)"))
        XCTAssertTrue(tabSource.contains("private func completeBackendRetryReadiness() async"))
        XCTAssertTrue(tabSource.contains("appState.startBackendHeartbeat()"))
        XCTAssertTrue(tabSource.contains("await KnownLibraryRegistryStore.shared.refresh()"))
        XCTAssertTrue(tabSource.contains("await libraryManager.backendDidBecomeReady()"))

        XCTAssertTrue(connectionSource.contains("var onConnected: (@MainActor () async -> Void)?"))
        XCTAssertTrue(connectionSource.contains("await completeSuccessfulConnection()"))
        XCTAssertTrue(connectionSource.contains("await onConnected?()"))
    }

    func testDocumentTabViewForwardsArtifactServiceIntoContentView() throws {
        let tabSource = try Self.appSource("Views/Shell/DocumentTabView.swift")
        let contentViewSource = try Self.appSource("Views/ContentView.swift")
        let builderSource = try Self.appSource("Views/ContentView+ViewBuilders.swift")
        let requiredSnippets = [
            "@Environment(ArtifactServiceGenerated.self) var artifactService",
            "@Environment(EntityServiceGenerated.self) var entityService",
            "@Environment(KGCurationServiceGenerated.self) var kgCurationService",
            "@Environment(ArtifactStore.self) var artifactStore",
            "@Environment(EntityStore.self) var entityStore",
            "@Environment(ClaimStore.self) var claimStore",
            ".environment(artifactService)",
            ".environment(entityService)",
            ".environment(kgCurationService)",
            ".environment(artifactStore)",
            ".environment(entityStore)",
            ".environment(claimStore)",
            ".environmentObject(FeatureManager.shared)",
            "@Environment(WorkflowStreamService.self) var workflowStreamService",
            "@Environment(ResearchService.self) var researchService",
            "@Environment(ClaimFocusState.self) var claimFocusState",
            "@Environment(KGFocusState.self) var kgFocusState",
            ".environment(workflowStreamService)",
            ".environment(researchService)",
            ".environment(claimFocusState)",
            ".environment(kgFocusState)",
            "built after `selectCollection`",
            "never depends on accidental inheritance"
        ]

        for snippet in requiredSnippets {
            XCTAssertTrue(tabSource.contains(snippet), "Missing snippet: \(snippet)")
        }
        XCTAssertTrue(contentViewSource.contains("@EnvironmentObject var featureManager: FeatureManager"))
        XCTAssertTrue(contentViewSource.contains("@Environment(ArtifactServiceGenerated.self) var artifactService"))
        XCTAssertTrue(contentViewSource.contains("@Environment(EntityServiceGenerated.self) var entityService"))
        XCTAssertTrue(builderSource.contains(".environment(artifactService)"))
        XCTAssertTrue(builderSource.contains(".environment(entityService)"))
    }

    func testMacBackendSettingsShowsInlinePairingQrAndNoSheetAssumption() throws {
        let settingsSource = try Self.appSource("Views/Settings/BackendSettingsView.swift")
        let remoteAccessSource = try Self.appSource("Views/Settings/BackendSettingsRemoteAccessSection.swift")

        XCTAssertTrue(settingsSource.contains("BackendSettingsRemoteAccessSection()"))
        XCTAssertTrue(remoteAccessSource.contains("Section(\"Remote Access\")"))
        XCTAssertTrue(remoteAccessSource.contains("Pair a Device"))
        XCTAssertTrue(remoteAccessSource.contains("Preparing pairing QR"))
        XCTAssertTrue(remoteAccessSource.contains("Advanced / Debug"))
        XCTAssertTrue(remoteAccessSource.contains("Pairing QR code"))
        XCTAssertTrue(remoteAccessSource.contains("Text(pairingCode.code)"))
        XCTAssertTrue(remoteAccessSource.contains("Expires \\(pairingCode.expiresAt.formatted"))
        XCTAssertTrue(remoteAccessSource.contains("activePairedDevices(from: pairedDevices)"))
        XCTAssertFalse(remoteAccessSource.contains("Show Pairing QR"))
        XCTAssertFalse(remoteAccessSource.contains("Generate Pairing QR"))
        XCTAssertFalse(remoteAccessSource.contains(".sheet(isPresented:"))
        XCTAssertFalse(remoteAccessSource.contains("QRCodeScannerSheet"))
    }

    func testBackendSettingsAppliesValidEngineHostAndShowsInvalidURL() throws {
        let settingsSource = try Self.appSource("Views/Settings/BackendSettingsView.swift")
        let libraryManagerSource = try Self.appSource("Models/LibraryManager.swift")
        let storageSource = try Self.appSource("Services/StorageServiceGenerated.swift")

        XCTAssertTrue(settingsSource.contains("Text(\"Invalid URL\")"))
        XCTAssertTrue(settingsSource.contains(".disabled(hostIsInvalid)"))
        XCTAssertTrue(settingsSource.contains("appState.reconfigureGeneratedClientsForCurrentHost()"))
        XCTAssertTrue(settingsSource.contains("libraryManager.reconfigureGeneratedClientsForCurrentHost()"))
        XCTAssertTrue(libraryManagerSource.contains("storageService.clearAll()"))
        XCTAssertTrue(storageSource.contains("func clearAll()"))
    }

    func testRemotePreviewSurfacesDoNotInventLocalFileURLs() throws {
        let imageViewerSource = try Self.appSource("Views/Library/ImageViewerComponents.swift")
        let activitySource = try Self.appSource("Views/Activity/ActivityProgressView+HistoricalProgress.swift")
        let trackingSource = try Self.appSource("Views/Library/ImageViewer/ImageWithCursorTracking.swift")

        XCTAssertFalse(imageViewerSource.contains("URL(fileURLWithPath: \"/\")"))
        XCTAssertFalse(activitySource.contains("URL(fileURLWithPath: filePath)"))
        XCTAssertTrue(activitySource.contains("(filePath as NSString).lastPathComponent"))
        XCTAssertTrue(trackingSource.contains("let url: URL?"))
        XCTAssertTrue(trackingSource.contains("url.flatMap(loadSDRImage)"))
    }

    func testNotesLiveInDocumentInspectorAndStandaloneBrowserRetired() throws {
        // Notes moved into the per-document inspector (Notes tab → DocumentNotesTab,
        // #1500). The standalone library-wide browser sheet and its Data-menu entry
        // are retired.
        let menuSource = try Self.appSource("FicheroApp.swift")
        let appStateSource = try Self.appSource("App/AppState.swift")
        let windowSource = try Self.appSource("App/LibraryWindow.swift")
        let inspectorSource = try Self.appSource("Views/Library/DocumentInspector.swift")

        // The Notes tab routes to the per-document notes view.
        XCTAssertTrue(inspectorSource.contains("DocumentNotesTab(document: doc)"))

        // The standalone browser sheet, its menu entry, and its driver are gone.
        XCTAssertFalse(appStateSource.contains("showNotesBrowser"))
        XCTAssertFalse(menuSource.contains("Notes Browser…"))
        XCTAssertFalse(menuSource.contains("showNotesBrowser"))
        XCTAssertFalse(windowSource.contains("NotesBrowserView()"))
        XCTAssertFalse(windowSource.contains("showNotesBrowser"))
    }

    // MARK: - ActivityChildType

    func testActivityChildTypeRawValuesStable() {
        XCTAssertEqual(ActivityChildType.console.rawValue, "console")
        XCTAssertEqual(ActivityChildType.progress.rawValue, "progress")
        XCTAssertEqual(ActivityChildType.log.rawValue, "log")
    }

    func testActivityChildTypeAllCasesCount() {
        XCTAssertEqual(ActivityChildType.allCases.count, 3)
    }

    func testActivityChildTypeLabels() {
        let pairs: [(ActivityChildType, String)] = [
            (.console, "Console"), (.progress, "Progress"),
            (.log, "Log")
        ]
        for (kind, label) in pairs {
            XCTAssertEqual(kind.label, label, "kind=\(kind.rawValue)")
        }
    }

    func testActivityChildTypeIcons() {
        // SF Symbols — drift here breaks the Report Navigator sidebar.
        let pairs: [(ActivityChildType, String)] = [
            (.console, "text.alignleft"),
            (.progress, "chart.bar.fill"),
            (.log, "doc.text")
        ]
        for (kind, icon) in pairs {
            XCTAssertEqual(kind.icon, icon, "kind=\(kind.rawValue)")
        }
    }

    // MARK: - SelectedActivityRun.with(childType:)

    func testSelectedActivityRunWithReplacesChildType() {
        let original = SelectedActivityRun(
            id: "r-1", name: "Run", workflowId: "wf-1",
            threadId: "t-1", timestamp: Date(timeIntervalSince1970: 0),
            status: .running, isLive: true, childType: nil
        )
        let updated = original.with(childType: .progress)
        XCTAssertEqual(updated.id, original.id)
        XCTAssertEqual(updated.name, original.name)
        XCTAssertEqual(updated.workflowId, original.workflowId)
        XCTAssertEqual(updated.threadId, original.threadId)
        XCTAssertEqual(updated.timestamp, original.timestamp)
        XCTAssertEqual(updated.status, original.status)
        XCTAssertEqual(updated.isLive, original.isLive)
        XCTAssertEqual(updated.childType, .progress)
        XCTAssertNil(original.childType)  // immutability of original
    }

    func testSelectedActivityRunWithCanClearChildType() {
        let original = SelectedActivityRun(
            id: "r-1", name: "Run", workflowId: nil,
            threadId: nil, timestamp: Date(timeIntervalSince1970: 0),
            status: .completed, isLive: false, childType: .log
        )
        let cleared = original.with(childType: nil)
        XCTAssertNil(cleared.childType)
    }

    func testActivityRunStatusTypeRawValues() {
        XCTAssertEqual(SelectedActivityRun.ActivityRunStatusType.running.rawValue, "running")
        XCTAssertEqual(SelectedActivityRun.ActivityRunStatusType.completed.rawValue, "completed")
        XCTAssertEqual(SelectedActivityRun.ActivityRunStatusType.failed.rawValue, "failed")
        XCTAssertEqual(SelectedActivityRun.ActivityRunStatusType.cancelled.rawValue, "cancelled")
    }

    // MARK: - Helpers

    private func makeDoc(id: String, name: String, childCount: Int = 0) -> Document {
        Document(
            id: id, parentId: nil, docType: .folder,
            fileType: nil, name: name, path: nil,
            sequence: nil, bbox: nil, status: .completed,
            metadata: [:], pageContent: nil,
            childCount: childCount,
            createdAt: Date(), updatedAt: Date()
        )
    }
}

/// File-local URLProtocol stub for the batch-column-metadata store tests
/// (#3758). A dedicated class — not the shared `MockURLProtocol` — so its
/// static handler can never collide with another suite running in parallel.
private final class ColumnsStubURLProtocol: URLProtocol {
    nonisolated(unsafe) static var handler: ((URLRequest) throws -> (HTTPURLResponse, Data))?

    override static func canInit(with request: URLRequest) -> Bool { true }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let handler = Self.handler else {
            client?.urlProtocol(self, didFailWithError: URLError(.notConnectedToInternet))
            return
        }
        do {
            let (response, data) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}
// swiftlint:enable file_length
