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
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    // Note: DocumentCreateRequest / DocumentUpdateRequest were removed in #3030
    // (create/update now go through DocumentService →
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

    func testDocumentStoreLoadsSidebarRootsThroughGeneratedService() throws {
        let source = try Self.appSource("Models/DocumentStore.swift")

        XCTAssertTrue(source.contains("documentService.getRoots()"))
        XCTAssertFalse(source.contains("api.get(\"/documents\""))
        XCTAssertFalse(source.contains("api.post(\"/documents\""))
    }

    // MARK: - #3355 one-level chevron prefetch

    func testSidebarPrefetchesOneLevelDownForChevrons() throws {
        // The backend never sends child_count, so a folder's disclosure chevron
        // only renders once its children are cached. The fix prefetches one level
        // down at both load seams so "a folder of folders" shows its triangles.
        let store = try Self.appSource("Models/DocumentStore.swift")
        let prefetch = try Self.appSource("Models/DocumentStore+SidebarPrefetch.swift")
        // Root load prefetches so top-level folders show chevrons before a click.
        XCTAssertTrue(store.contains("prefetchChildContainerChildren(of: collections)"))
        // Expanding a folder caches its children AND one level deeper.
        XCTAssertTrue(prefetch.contains("cacheSidebarChildren(of: document)"))
        XCTAssertTrue(prefetch.contains("prefetchChildContainerChildren(of: children)"))
        // Only containers are prefetched — leaf rows have nothing to reveal.
        // (The batching refactor moved the guard from a `for … where` clause
        // into `containersNeedingChildren`'s filter.)
        XCTAssertTrue(prefetch.contains("$0.docType == .folder"))
    }

    func testSidebarRowOptionClickExpandsWholeSubtree() throws {
        let source = try Self.appSource("Views/Sidebar/ItemRow/SidebarItemRow.swift")
        // Option-click on the chevron expands the entire subtree (Finder-style).
        XCTAssertTrue(source.contains("modifierFlags.contains(.option)"))
        XCTAssertTrue(source.contains("func expandSubtree("))
        // The dead childCount>0 gate (backend never sends child_count) is gone.
        XCTAssertFalse(source.contains("document.childCount > 0"))
    }

    // MARK: - Batch library-item column metadata (#3758)

    /// Test seam: a DocumentStore whose generated client is bound to a stubbed
    /// URLProtocol session, so `libraryItemColumns` exercises the real
    /// request/response mapping without a live engine.
    @MainActor
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
        // #3917 TODO: the generated client's POST-with-body path uses
        // URLSession.upload(for:from:), which the ColumnsStubURLProtocol stub
        // does not intercept (URLProtocol upload-task limitation), so this hits
        // the real network (-1003). The stub wiring itself is correct — the
        // short-circuit sibling test passes. Skip until the mock transport
        // covers upload tasks (or the test moves to EngineHarness).
        throw XCTSkip("generated-client upload-task path bypasses URLProtocol stub — mock-infra gap (#3917)")
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

        let store = await Self.makeStubbedStore()
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

        let store = await Self.makeStubbedStore()
        let rows = try await store.libraryItemColumns(itemIds: [])

        XCTAssertTrue(rows.isEmpty)
    }

    // MARK: - AppViewMode.category

    func testAppViewModeCategoryRouting() {
        // Locks the sidebar-to-toolbar wire: each AppViewMode collapses
        // into an ItemCategory used to decide which toolbar set renders.
        XCTAssertEqual(AppViewMode.library(nil).category, .folder)
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
        // Routing moved off SidebarView into the typed SidebarDestination switch
        // in SidebarView+SelectionHandling.swift (browser(.entities) case); the
        // `case .browser(.entities):` mapping itself lives in SidebarStateManagers.swift.
        let source = try [
            Self.appSource("Views/Sidebar/Sections/SidebarView+SelectionHandling.swift"),
            Self.appSource("Views/Sidebar/State/SidebarStateManagers.swift")
        ].joined(separator: "\n")

        XCTAssertTrue(source.contains("case .browser(.entities):"))
        XCTAssertTrue(source.contains("sidebarMode = .library"))
        XCTAssertTrue(source.contains("viewMode = .library(nil)"))
    }

    func testPinnedBottomNavigationRowsAreRetired() throws {
        // #4102: everything in the sidebar is a node under its library; the
        // pinned Workflows / Chat with Docs / Research / Workspaces / Entities
        // bottom rows are gone. App-level surfaces route via the View menu.
        let source = try Self.appSource("Views/Sidebar/Sections/SidebarView+PinnedNavigationRows.swift")

        XCTAssertFalse(source.contains("tag: .browser(.entities)"))
        XCTAssertFalse(source.contains("Chat with Docs"))
        XCTAssertFalse(source.contains("tag: .browser(.workflows)"))
        XCTAssertFalse(source.contains("tag: .browser(.research)"))
        XCTAssertFalse(source.contains("Text(\"Workspaces\")"))
        // The automation load-error surface is the one thing that stays.
        XCTAssertTrue(source.contains("Automation Unavailable"))
    }

    func testEntityLibrarySelectionLocksDisplayModeToList() throws {
        // file_length: ContentView+State split into ContentView+State*; read them all concatenated.
        let stateSource = try [
            Self.appSource("Views/Shell/ContentView/ContentView+StateDisplay.swift"),
            Self.appSource("Views/Shell/ContentView/ContentView+StateSelection.swift"),
            Self.appSource("Views/Shell/ContentView/ContentView+StateLayout.swift"),
            Self.appSource("Views/Shell/ContentView/ContentView+StatePreview.swift"),
            Self.appSource("Views/Shell/ContentView/ContentView+StateEvents.swift"),
        ].joined(separator: "\n")

        XCTAssertTrue(stateSource.contains("var isEntityLibrarySelection: Bool"))
        XCTAssertTrue(stateSource.contains("if isEntityLibrarySelection {"))
        XCTAssertTrue(stateSource.contains("return [.list]"))
        XCTAssertTrue(stateSource.contains("if newFolderId == \"entities-browser\""))
        XCTAssertTrue(stateSource.contains("viewDisplayMode = .list"))
    }

    func testEntityLibrarySelectionRoutesBrowserSelectionIntoKGFocus() throws {
        // file_length: ContentView+State split into ContentView+State*; read them all concatenated.
        let stateSource = try [
            Self.appSource("Views/Shell/ContentView/ContentView+StateDisplay.swift"),
            Self.appSource("Views/Shell/ContentView/ContentView+StateSelection.swift"),
            Self.appSource("Views/Shell/ContentView/ContentView+StateLayout.swift"),
            Self.appSource("Views/Shell/ContentView/ContentView+StatePreview.swift"),
            Self.appSource("Views/Shell/ContentView/ContentView+StateEvents.swift"),
        ].joined(separator: "\n")
        let navigationSource = try Self.appSource("Views/Shell/ContentView/ContentView+Navigation.swift")

        XCTAssertTrue(stateSource.contains("if isEntityLibrarySelection {"))
        XCTAssertTrue(stateSource.contains("kgFocusState.focusEntity(entityId: firstId)"))
        XCTAssertTrue(stateSource.contains("kgFocusState.clear()"))
        XCTAssertTrue(navigationSource.contains("contentCollection: isEntityLibrarySelection ? .entities : .documents"))
    }

    func testPinnedSidebarEntryPointsRouteToExpectedSurfaces() throws {
        // Typed SidebarDestination routing (SidebarView+SelectionHandling.swift);
        // the `case .browser(...)` mappings themselves live in SidebarStateManagers.swift.
        let source = try [
            Self.appSource("Views/Sidebar/Sections/SidebarView+SelectionHandling.swift"),
            Self.appSource("Views/Sidebar/State/SidebarStateManagers.swift")
        ].joined(separator: "\n")

        XCTAssertTrue(source.contains("case .browser(.comparison):"))
        XCTAssertTrue(source.contains("viewMode = .comparison(nil)"))
        XCTAssertTrue(source.contains("case .browser(.research):"))
        XCTAssertTrue(source.contains("sidebarMode = .research"))
    }

    // testSidebarDisclosureRowsDisableNestedInsertionAnimation retired: the
    // nested-insertion animation suppression (#3165) was consciously dropped
    // when per-library sub-sections collapsed into one flat unified row list
    // (edd399fbe / #4059) — rows now insert at the top level, so the lateral
    // reveal-origin artifact it guarded against can no longer occur.

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
        let source = try Self.appSource("Views/Shell/ContentView/ContentView+Navigation.swift")

        XCTAssertTrue(source.contains("Keep the library surface inside the content column"))
        XCTAssertTrue(source.contains(".clipped()"))
        XCTAssertTrue(source.contains("under the shell sidebar or off the left window edge"))
    }

    func testDetailShellColumnClipsAllPreviewLayoutsToItsBounds() throws {
        let source = try ([
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+RootLayout.swift"),
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+InspectorContainer.swift"),
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+SidebarLayout.swift"),
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+DetailLayout.swift"),
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+CompactReader.swift"),
        ].joined(separator: "\n"))

        XCTAssertTrue(source.contains("Keep every library/preview/reader combination inside the detail"))
        XCTAssertTrue(source.contains("column bounds. Without this outer clip"))
        XCTAssertTrue(source.contains(".background(Color(platformColor: .textBackgroundColor))"))
        XCTAssertTrue(source.contains(".clipped()"))
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
        let toolbarSource = try Self.appSource("Views/Shell/ContentView/ContentView+Toolbar.swift")
        // #4024: Show/Hide Library Browser pane-toggle copy moved to ViewMenuPaneSections.swift.
        let menuSource = try Self.appSource("App/Menus/ViewMenuPaneSections.swift")

        XCTAssertTrue(toolbarSource.contains("placement: .principal"))
        XCTAssertTrue(toolbarSource.contains("LibraryManager.shared.getLibrary(id: windowState.libraryId)?.displayName"))
        XCTAssertTrue(toolbarSource.contains("Text(libraryName)"))
        XCTAssertTrue(menuSource.contains("Show Library Browser"))
        XCTAssertTrue(menuSource.contains("Hide Library Browser"))
        XCTAssertTrue(menuSource.contains("icon: \"books.vertical\""))
    }

    func testIpadViewMenuUsesSharedViewCommands() throws {
        let contentSource = try Self.appSource("Views/Shell/ContentView/ContentView+Toolbar.swift")

        XCTAssertTrue(contentSource.contains("ViewMenuCommands()"))
        // #4360: the glyph now comes from the ToolbarSymbols uniqueness policy.
        XCTAssertTrue(contentSource.contains("Label(\"View\", systemImage: ToolbarSymbols.viewMenu)"))
    }

    func testEngineLaunchSequenceIsOwnedByLifecycleController() throws {
        // #3945: the engine launch sequence is owned by EngineLifecycleController
        // (app-scoped), NOT by FicheroApp / a window. Assert the sequence lives
        // there, in order: spawn → readiness probe → heartbeat → library-ready
        // side-effects. (Rewritten from the old FicheroApp-grep version, which went
        // stale when PR #1 moved this orchestration off the window.)
        let controllerSource = try Self.appSource("Services/EngineLifecycleController.swift")

        guard
            let startRange = controllerSource.range(of: "try await backendService.start()"),
            let probeRange = controllerSource.range(
                of: "checkBackendHealthUntilReady(",
                range: startRange.upperBound..<controllerSource.endIndex
            ),
            let heartbeatRange = controllerSource.range(
                of: "appState.startBackendHeartbeat()",
                range: probeRange.upperBound..<controllerSource.endIndex
            ),
            let readyRange = controllerSource.range(
                of: "await libraryManager.refreshAfterBackendBecameReady()",
                range: heartbeatRange.upperBound..<controllerSource.endIndex
            )
        else {
            return XCTFail("engine launch sequence changed unexpectedly in EngineLifecycleController")
        }

        XCTAssertLessThan(startRange.lowerBound, probeRange.lowerBound)
        XCTAssertLessThan(probeRange.lowerBound, heartbeatRange.lowerBound)
        XCTAssertLessThan(heartbeatRange.lowerBound, readyRange.lowerBound)

        // Ownership moved off the window (#3945): FicheroApp must NOT spawn the
        // engine anymore — that's the whole point of the app-owns-engine change.
        let appSource = try Self.appSource("FicheroApp.swift")
        XCTAssertFalse(
            appSource.contains("try await backendService.start()"),
            "FicheroApp still spawns the engine — it must be owned by EngineLifecycleController (#3945)"
        )
    }

    @MainActor
    func testIsRetriableLoadFailureSeparatesTransientFromDefinitive() {
        // #3972: one transient blip must NOT trip the app-wide outage pane, so
        // transient engine-unreachable / transport failures are retriable…
        XCTAssertTrue(DocumentStore.isRetriableLoadFailure(URLError(.timedOut)))
        XCTAssertTrue(DocumentStore.isRetriableLoadFailure(URLError(.cannotConnectToHost)))
        // …while a definitive TLS-pin failure surfaces immediately (not retriable).
        XCTAssertFalse(DocumentStore.isRetriableLoadFailure(URLError(.secureConnectionFailed)))
    }

    func testBackendRetryRunsSameReadinessSideEffectsAsStartup() throws {
        // Retry and startup converge on one path: EngineLifecycleController.retry()
        // re-enters connect(restart:) and success always runs the single
        // finishSuccessfulConnect readiness block (#3108/#3113). The UI reaches
        // it via the engineRetry environment entry point.
        let lifecycleSource = try Self.appSource("Services/EngineLifecycleController.swift")
        let appSource = try Self.appSource("FicheroApp.swift")
        let connectionSource = try [
            Self.appSource("Views/Components/BackendConnection/BackendConnectionView.swift"),
            Self.appSource("Views/Components/BackendConnection/BackendConnectionView+Actions.swift")
        ].joined(separator: "\n")

        XCTAssertTrue(lifecycleSource.contains("func retry() async {"))
        XCTAssertTrue(lifecycleSource.contains("await connect(restart: true)"))
        XCTAssertTrue(lifecycleSource.contains("private func finishSuccessfulConnect(backendStart: Date) async"))
        XCTAssertTrue(lifecycleSource.contains("appState.startBackendHeartbeat()"))
        XCTAssertTrue(lifecycleSource.contains("await libraryManager.refreshAfterBackendBecameReady()"))

        XCTAssertTrue(appSource.contains(".environment(\\.engineRetry, { await appDelegate.controller.retry() })"))

        XCTAssertTrue(connectionSource.contains("var onRetry: (@MainActor () async -> Void)?"))
        XCTAssertTrue(connectionSource.contains("await onRetry?()"))
    }

    func testDocumentTabViewForwardsArtifactServiceIntoContentView() throws {
        let tabSource = try Self.appSource("Views/Shell/DocumentTabView.swift")
        let contentViewSource = try Self.appSource("Views/Shell/ContentView/ContentView.swift")
        let builderSource = try ([
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+RootLayout.swift"),
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+InspectorContainer.swift"),
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+SidebarLayout.swift"),
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+DetailLayout.swift"),
            Self.appSource("Views/Shell/ContentView/Layout/ContentView+CompactReader.swift"),
        ].joined(separator: "\n"))
        let requiredSnippets = [
            "@Environment(ArtifactService.self) var artifactService",
            "@Environment(EntityService.self) var entityService",
            "@Environment(KGCurationService.self) var kgCurationService",
            "@Environment(ArtifactStore.self) var artifactStore",
            "@Environment(EntityStore.self) var entityStore",
            "@Environment(ClaimStore.self) var claimStore",
            ".environment(artifactService)",
            ".environment(entityService)",
            ".environment(kgCurationService)",
            ".environment(artifactStore)",
            ".environment(entityStore)",
            ".environment(claimStore)",
            ".environment(FeatureManager.shared)",
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
        XCTAssertTrue(contentViewSource.contains("@Environment(FeatureManager.self) var featureManager"))
        XCTAssertTrue(contentViewSource.contains("@Environment(ArtifactService.self) var artifactService"))
        XCTAssertTrue(contentViewSource.contains("@Environment(EntityService.self) var entityService"))
        XCTAssertTrue(builderSource.contains(".environment(artifactService)"))
        XCTAssertTrue(builderSource.contains(".environment(entityService)"))
    }

    func testMacBackendSettingsShowsInlinePairingQrAndNoSheetAssumption() throws {
        // The pairing surface moved into ShareSettingsView, which renders the
        // inline PairingCardView / PairedDevicesSectionView (defined in
        // PairingCardView.swift). No sheet, no scanner.
        let shareSource = try Self.appSource("Views/Settings/Sharing/Share/ShareSettingsView.swift")
        let remoteAccessSource = try Self.appSource("Views/Settings/Sharing/PairingCardView.swift")

        XCTAssertTrue(shareSource.contains("PairingCardView("))
        XCTAssertTrue(shareSource.contains("PairedDevicesSectionView("))
        XCTAssertTrue(shareSource.contains("activePairedDevices(from: pairedDevices)"))
        XCTAssertTrue(remoteAccessSource.contains("ProgressView(\"Preparing QR code…\")"))
        XCTAssertTrue(remoteAccessSource.contains(".accessibilityLabel(\"Pairing QR code\")"))
        XCTAssertTrue(remoteAccessSource.contains("Expires \\(pairingCode.expiresAt.formatted"))
        XCTAssertFalse(remoteAccessSource.contains("Show Pairing QR"))
        XCTAssertFalse(remoteAccessSource.contains("Generate Pairing QR"))
        XCTAssertFalse(remoteAccessSource.contains(".sheet(isPresented:"))
        XCTAssertFalse(remoteAccessSource.contains("QRCodeScannerSheet"))
    }

    func testBackendSettingsAppliesValidEngineHostAndShowsInvalidURL() throws {
        let settingsSource = try Self.appSource("Views/Settings/Engine/BackendSettingsView.swift")
        let libraryManagerSource = try Self.appSource("Models/LibraryManager.swift")
        let storageSource = try Self.appSource("Services/StorageService.swift")

        XCTAssertTrue(settingsSource.contains("Text(\"Invalid URL\")"))
        XCTAssertTrue(settingsSource.contains(".disabled(hostIsInvalid)"))
        XCTAssertTrue(settingsSource.contains("appState.reconfigureGeneratedClientsForCurrentHost()"))
        XCTAssertTrue(settingsSource.contains("libraryManager.reconfigureGeneratedClientsForCurrentHost()"))
        XCTAssertTrue(libraryManagerSource.contains("storageService.clearAll()"))
        XCTAssertTrue(storageSource.contains("func clearAll()"))
    }

    func testRemotePreviewSurfacesDoNotInventLocalFileURLs() throws {
        // file_length: ImageViewerComponents/ImageWithCursorTracking split; assertions repointed to the files that hold the URL logic now.
        let imageViewerSource = try Self.appSource("Views/Preview/ImageViewer/ZoomableImagePreviewMac.swift")
        let activitySource = try Self.appSource("Views/Activity/Progress/ActivityProgressView+HistoricalProgress.swift")
        let trackingSource = try Self.appSource("Views/Preview/ImageViewer/CursorTracking/ImageWithCursorTrackingMac.swift")

        XCTAssertFalse(imageViewerSource.contains("URL(fileURLWithPath: \"/\")"))
        XCTAssertFalse(activitySource.contains("URL(fileURLWithPath: filePath)"))
        XCTAssertTrue(activitySource.contains("(filePath as NSString).lastPathComponent"))
        XCTAssertTrue(trackingSource.contains("let url: URL?"))
        XCTAssertTrue(trackingSource.contains("loadImageAsync(url: url"))
    }

    func testNotesLiveInDocumentInspectorAndStandaloneBrowserRetired() throws {
        // Notes moved into the per-document inspector (Notes tab → DocumentNotesTab,
        // #1500). The standalone library-wide browser sheet and its Data-menu entry
        // are retired.
        let menuSource = try Self.appSource("FicheroApp.swift")
        let appStateSource = try Self.appSource("App/AppState.swift")
        let windowSource = try Self.appSource("App/LibraryWindow.swift")
        // #4024: the Notes tab wiring (DocumentNotesTab(document: doc)) now lives in
        // DocumentInspector+Sections.swift, split out of DocumentInspector.swift.
        let inspectorSource = try Self.appSource("Views/Inspector/Document/DocumentInspector+Sections.swift")

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
        // console, progress, log + the run-trace graph (#4320)
        XCTAssertEqual(ActivityChildType.allCases.count, 4)
    }

    func testActivityChildTypeLabels() {
        let pairs: [(ActivityChildType, String)] = [
            (.console, "Console"), (.progress, "Progress"),
            (.log, "Log"), (.trace, "Trace")
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
