import Combine
import FicheroAPIClient
import OSLog
import SwiftUI
import UniformTypeIdentifiers

enum LibraryContentCollection {
    case documents
    case entities
}

/// Grid/List/Table/Map view of documents
struct LibraryView: View {
    let documents: [Document]
    let contentCollection: LibraryContentCollection
    let isLoading: Bool
    let isConnected: Bool
    let errorMessage: String?
    let onRetry: () -> Void
    /// Sort field / direction / filter-bar visibility, lifted out of @State so
    /// the in-content mode rail can drive them too (#1477). Owned by ContentView.
    @Bindable var libraryToolbar: LibraryToolbarState
    @Binding var selection: Set<String>
    @Binding var detailDocument: Document?
    @Binding var viewMode: LibraryLayout
    var isPaneFocused: Bool = false
    let displayMode: ViewDisplayMode  // Universal view mode from toolbar

    let folderId: String?  // Current folder ID for per-folder sort persistence
    var onRequestFocus: () -> Void = {}  // Called on tap to pull keyboard focus into content area
    var onRequestPreviousPaneFocus: () -> Void = {}  // Left arrow in list/table — move to sidebar
    var onRequestNextPaneFocus: () -> Void = {}  // Right arrow in list/table — move to inspector
    var onNavigateInto: (Document) -> Void = { _ in }  // Double-click on folder/PDF — navigate into it
    /// Called when a page item row is selected in the outline table (#2405).
    /// Callers should set `pageFocusDocument` to drive reader + inspector focus.
    var onPageFocus: (Document) -> Void = { _ in }
    /// When the sidebar is hidden, single-click in the grid acts like Finder
    /// (no-sidebar fallback): plain click navigates INTO navigable containers
    /// instead of just selecting. Modified clicks (Shift/Cmd) still select
    /// only — you can't have a multi-select if one click navigates away.
    /// (#786)
    var sidebarHidden: Bool = false
    /// Submit handler for the toolbar search field. ContentView wires
    /// this to runToolbarSearch so typing+Return in library mode fires
    /// a global search and switches the sidebar into search mode —
    /// matches the behaviour of every other mode-specific .searchable.
    var onToolbarSearchSubmit: (String) -> Void = { _ in }

    @State var searchText: String = ""
    /// Precomputed lowercased ⌘F search keys per docId (#3865). Rebuilt only when
    /// the document set changes, so keystroke filtering is a dict lookup, not a
    /// fresh full-OCR scan. See `rebuildDocumentSearchKeys`.
    @State var documentSearchKeys: [String: String] = [:]
    /// Bottom-bar file import presenter (#2313).
    @State var showingFileImporter = false
    @FocusState var filterFieldFocused: Bool
    @State var sortOrder: [KeyPathComparator<Document>] = [.init(\.name, order: .forward)]
    @SceneStorage("library.sortFieldsByFolder") var sortFieldsByFolderJSON: String = "{}"
    @SceneStorage("library.sortAscendingByFolder") var sortAscendingByFolderJSON: String = "{}"

    // Workflow picker state
    @State var showWorkflowPicker = false
    @State var selectedDocumentIdsForBatch: [String] = []

    /// Document pending presentation in the Add-to-Workspace picker (#1494).
    /// Non-nil drives the `.sheet(item:)` below.
    @State var workspacePickerDocument: Document?
    /// Non-nil presents the bookmark sheet for this document (#2755).
    @State var bookmarkPickerDocument: Document?

    @Environment(AppState.self) var appState
    @Environment(LibraryManager.self) var libraryManager
    @Environment(WindowState.self) var windowState
    /// Finder-style Open in New Tab / New Window opens a fresh window on the
    /// current library via the Safari new-window path (#1685).
    @Environment(\.openWindow) var openWindow
    @Environment(WorkflowStreamService.self) var workflowStreamService
    @Environment(DocumentStore.self) var documentStore: DocumentStore
    @Environment(EntityService.self) var entityService
    @Environment(ArtifactService.self) var artifactService
    @Environment(WorkflowExecutionObserver.self) var executionObserver
    @Environment(KGFocusState.self) var kgFocusState
    let featureManager = FeatureManager.shared
    @State var workflowRunProviderCache = WorkflowRunProviderCache.shared

    // Column visibility for Table view (persisted per-window/scene)
    @SceneStorage("column_name") var showName = true
    @SceneStorage("column_status") var showStatus = true
    @SceneStorage("column_progress") var showProgress = true
    @SceneStorage("column_output") var showOutput = true
    @SceneStorage("column_fileType") var showFileType = true
    @SceneStorage("column_path") var showPath = false
    @SceneStorage("column_createdDate") var showCreatedDate = true
    @SceneStorage("column_modifiedDate") var showModifiedDate = false
    @SceneStorage("column_size") var showSize = false
    @SceneStorage("column_artifacts") var showArtifacts = false  // #519: hidden by default

    // Per-entity-type visibility flags for the list-view lozenge rows.
    // Now driven by the same @AppStorage CSV used by the KG ontology
    // browser + document-inspector KG tab so toggling People in any
    // surface affects all of them. The CSV stores HIDDEN EntityType
    // raw values ("person", "location", "organization", "event",
    // "concept", "other"); empty CSV = show everything. (#887)
    @AppStorage("inspector.kg.hiddenKinds") var hiddenKindsCSV: String = ""

    // "dates" doesn't have a KnowledgeEntity counterpart (dates are
    // surfaced via the timeline tool, not as KG entities) so the dates
    // lozenge stays on a Library-only @SceneStorage flag.
    @SceneStorage("list_show_dates") var showDatesEntities = true

    /// Mac-native column customization for the table view (right-click on
    /// any column header → show/hide menu, drag to reorder). Backed by
    /// SwiftUI's TableColumnCustomization API on macOS 14+. State lives
    /// for the window lifetime; deeper persistence to @SceneStorage is a
    /// follow-up. (#519)
    @State var tableColumnCustomization = TableColumnCustomization<LibraryOutlineNode>()

    /// Drives the expandable outline Table (#2258). Lazily created on
    /// first appear (needs the library's entity service from the
    /// environment); caches per-document rollup counts so collapsed rows
    /// can show "12 entities, 3 notes" without fetching the children.
    @State var outlineModel: LibraryOutlineModel?
    /// Disclosure expansion state for the outline Table, keyed by node id
    /// (document id). Expanding a document triggers its rollup fetch.
    @State var outlineExpanded: Set<String> = []
    /// Compact width (iPhone) drops the macOS/iPadOS `DisclosureTableRow`
    /// outline for a plain document list — `Table` disclosure is a
    /// regular-width affordance.
    @Environment(\.horizontalSizeClass) var horizontalSizeClass

    @State var entities: [Components.Schemas.KnowledgeEntity] = []
    @State private var spatialSelectedNodeId: String?
    @State private var cachedLibraryProjection = SpatialLibraryProjection(nodes: [], links: [])

    @State var isLoadingEntities = false
    @State var entityLoadErrorMessage: String?

    // ponytail: recompute inputs — documents, entities, searchText, sortOrder, sortFieldRaw, sortAscending, folderId
    // Not `private`: recomputeFiltered() lives in the LibraryView+FilterAndBatch.swift
    // extension (a different file), so these must be at least internal to be visible there.
    @State var filteredDocuments: [Document] = []
    @State var filteredEntities: [Components.Schemas.KnowledgeEntity] = []
    /// Stable key for .onChange in iconsView — updated inside recomputeFiltered()
    /// to reset thumbnail prefetch state when the visible document set changes. A
    /// hash of the ids (Int), not a joined String of every id (#3870).
    @State var thumbnailPrefetchKey: Int = 0
    /// id → index in `filteredDocuments`, rebuilt in recomputeFiltered() so
    /// prefetch scheduling is an O(1) lookup, not an O(n) firstIndex per cell (#3870).
    @State var documentIndexById: [String: Int] = [:]
    @State var prefetchedThumbnailIds: Set<String> = []
    @State var thumbnailPrefetchTask: Task<Void, Never>?

    // Delete confirmation state
    @State var showDeleteConfirmation = false
    @State var documentsToDelete: [Document] = []

    // Inline rename state
    @State var renamingDocumentId: String?
    @State var editingName: String = ""

    // Type-to-select state
    @State var typeSelectBuffer: String = ""
    @State var typeSelectTask: Task<Void, Never>?

    // Keyboard scroll target for list view (set by arrow key nav, consumed by ScrollViewReader)
    // listScrollTarget = minimal scroll (anchor: nil) — used by arrow keys so we
    //   don't recenter on every keypress when the new item is already on-screen (#769).
    // listScrollCenterTarget = forced center scroll — used by double-click and other
    //   layout-changing actions where the user genuinely wants the item centered.
    @State var listScrollTarget: String?
    @State var listScrollCenterTarget: String?

    // Selection anchor for Shift+click range select
    @State var selectionAnchor: String?

    // Grid column count for arrow key navigation (updated by GeometryReader in iconsView)
    @State var gridColumnCount: Int = 4

    // Zoom scale for the icon view (persisted per-app)
    @AppStorage("library.iconViewScale") var iconViewScale: Double = 1.0
    // Captures iconViewScale at the start of a pinch so the gesture's
    // multiplier multiplies against the gesture-start size, not the
    // continuously-updating scale (which would compound exponentially).
    @State var pinchBaseScale: Double = 1.0

    // Degraded fallback only: live activity/change-stream signals now trigger
    // the surgical pending-status refresh immediately (#3200). Keep the timer
    // only while live updates are paused/unavailable.
    private let processingPollTimer = Timer.publish(every: 15, on: .main, in: .common).autoconnect()
    private var shouldUseProcessingPollFallback: Bool {
        guard let ref = scopedLibraryReference else { return false }
        return ref.changeStream.liveUpdatesUnavailable || ref.activityStore.liveUpdatesPaused
    }

    /// The library has never loaded and nothing has failed — startup, not an
    /// outage (#3937).
    private var isAwaitingFirstLoad: Bool {
        guard !isShowingEntitiesCollection else { return false }
        return Self.isAwaitingFirstLoad(hasLoadedSuccessfully: isConnected, error: documentStore.error)
    }

    /// A store that has never loaded is starting up, not offline (#3937).
    ///
    /// `DocumentStore.isConnected` only flips true once a load SUCCEEDS, so on its
    /// own it cannot tell "healthy but not asked for data yet" from "offline". The
    /// absence of an error is what separates the two — which is why this can never
    /// mask a real outage: the instant a load fails, `error` is set and the
    /// failure branches win.
    ///
    /// Pure so the invariant is testable without a live engine, the same reason
    /// `BackendConnectionView.connectionFailureTitle` is pure (#3341).
    static func isAwaitingFirstLoad(hasLoadedSuccessfully: Bool, error: Error?) -> Bool {
        !hasLoadedSuccessfully && error == nil
    }

    /// True only when a load failed because the engine could not be REACHED
    /// (#3937) — the one state that earns the outage pane. Every other failure
    /// keeps its own message via `errorState`, and no failure at all is not an
    /// outage. Reuses the one `AccessError` classifier instead of re-reading
    /// `URLError` codes here. An already-typed `AccessError` never arrives: the
    /// access-denied branch above claims it first.
    static func isEngineOutage(_ error: Error?) -> Bool {
        guard let error else { return false }
        return AccessError.classify(error) == .engineUnreachable
    }

    // Extracted from `body` to keep the body modifier chain within the Swift
    // type-checker's budget — adding the #2307 onChange handlers tipped the
    // single expression over "unable to type-check in reasonable time".
    // See memory: librarywindow-body-typecheck-timeout.
    @ViewBuilder
    private var libraryContent: some View {
        if isCollectionLoading || isAwaitingFirstLoad {
            loadingState
        } else if !isShowingEntitiesCollection, let denial = documentStore.error as? AccessError {
            // Never a silent 403 / blank pane (F6): a denied library read lands on
            // the explicit access state — which library, why, who you are, and the
            // next action — instead of the generic "couldn't load" text.
            LibraryAccessDeniedView(
                libraryName: libraryReference?.displayName ?? "this library",
                error: denial,
                identity: appState.identityStore,
                onRetry: { onRetry() },
                onSignIn: nil,
                onResetPin: { RemoteCertificatePinning.clearPersistedSPKIPin(hostString: EngineConfig.hostString) }
            )
        } else if !isShowingEntitiesCollection, Self.isEngineOutage(documentStore.error) {
            connectionErrorState
        } else if let activeErrorMessage {
            errorState(message: activeErrorMessage)
        } else if isCollectionEmpty {
            emptyState
        } else {
            switch displayMode {
            case .icon:
                iconsView
            case .list:
                listView
            case .table:
                tableView
            case .canvas, .workspace:
                canvasModeView
            case .space:
                spaceModeView
            }
        }
    }

    /// Move a dragged canvas node INTO a container via the audited `document.move`
    /// action (#3086). Maps spatial node ids → document ids; a non-document drag
    /// (canvas item) has no `doc:` id and is a safe no-op. The change stream
    /// reconciles both windows; a failure leaves the row put (never silent-drops).
    private func moveCanvasNodeIntoContainer(_ nodeId: String, _ containerNodeId: String) {
        guard let docId = SpatialLibraryProjector.documentId(fromNodeId: nodeId),
              let parentId = SpatialLibraryProjector.documentId(fromNodeId: containerNodeId) else { return }
        Task { @MainActor in
            _ = try? await documentStore.moveDocument(docId, toParent: parentId)
        }
    }

    @ViewBuilder
    private var spaceModeView: some View {
        if featureManager.isCanvasRealityKit3DEnabled {
            CanvasSpaceView(
                nodes: libraryProjection.nodes,
                connections: [],
                selectedNodeId: $spatialSelectedNodeId,
                layoutStore: canvasLayoutStore,
                itemStore: canvasItemStore,
                folderScopeId: folderId ?? wholeLibraryRoomId,
                containerIds: canvasContainerIds,
                moveIntoContainer: moveCanvasNodeIntoContainer
            )
        } else {
            SpaceSceneView(
                nodes: libraryProjection.nodes,
                connections: [],
                selectedNodeId: $spatialSelectedNodeId,
                layoutStore: canvasLayoutStore,
                itemStore: canvasItemStore,
                folderScopeId: folderId ?? wholeLibraryRoomId
            )
        }
    }

    /// The 2D Canvas renderer, gated (#3083): the new RealityKit-ortho
    /// `CanvasSceneView` when the flag is on, else the SwiftUI `Spatial2DCanvas`.
    /// Both read the SAME shared stores, so switching engines is transparent;
    /// the SwiftUI canvas is retired only at cutover (#3087). Extracted to keep
    /// `libraryContent`'s switch within the type-checker budget.
    @ViewBuilder
    private var canvasModeView: some View {
        if featureManager.isCanvasRealityKit2DEnabled {
            CanvasSceneView(
                nodes: libraryProjection.nodes,
                connections: [],
                selectedNodeId: $spatialSelectedNodeId,
                layoutStore: canvasLayoutStore,
                itemStore: canvasItemStore,
                folderScopeId: folderId ?? wholeLibraryRoomId,
                containerIds: canvasContainerIds,
                moveIntoContainer: moveCanvasNodeIntoContainer
            )
        } else {
            Spatial2DCanvas(
                nodes: libraryProjection.nodes,
                connections: [],
                selectedNodeId: $spatialSelectedNodeId,
                layoutStore: canvasLayoutStore,
                itemStore: canvasItemStore,
                folderScopeId: folderId ?? wholeLibraryRoomId
            )
        }
    }

    /// "Live updates paused" pill (F7), shown only when this library's change
    /// stream has dropped. Reading `stream.liveUpdatesUnavailable` (a nested
    /// @Observable) makes the pill appear/disappear reactively.
    @ViewBuilder
    private var liveUpdatesPausedInset: some View {
        if let ref = libraryReference {
            // Remote change delivery rides the activity stream (#3159/#2479), so
            // a 403 there means this device has no role on the library — a
            // terminal state with no reconnect (retrying can't mint access).
            if ref.changeStream.accessDenied || ref.activityStore.liveUpdatesAccessDenied {
                HStack {
                    Spacer(minLength: 0)
                    LiveUpdatesPausedPill(
                        message: "No access to live updates",
                        systemImage: "lock.slash",
                        onReconnect: nil
                    )
                    Spacer(minLength: 0)
                }
                .padding(.top, 8)
                .padding(.bottom, 4)
            } else if ref.changeStream.liveUpdatesUnavailable || ref.activityStore.liveUpdatesPaused {
                // Either the dedicated change stream (local) or the folded
                // activity stream (remote) dropped — say so instead of quietly
                // going stale, and offer a one-tap resubscribe of both.
                HStack {
                    Spacer(minLength: 0)
                    LiveUpdatesPausedPill(onReconnect: {
                        ref.changeStream.stop()
                        ref.changeStream.start()
                        ref.activityStore.reconnectLiveUpdates()
                    })
                    Spacer(minLength: 0)
                }
                .padding(.top, 8)
                .padding(.bottom, 4)
            }
        }
    }

    var body: some View {
        withKeyboardShortcuts(
            VStack(spacing: 0) {
                libraryContent
            }
            // No-silent-fallback (F7): if this library's change stream drops, say
            // so with a pill above the content instead of quietly showing stale
            // rows. Reserving real space keeps the first row from peeking
            // through behind the pill.
            .safeAreaInset(edge: .top, spacing: 0) {
                liveUpdatesPausedInset
            }
            // Xcode-navigator-style quick filter, pinned to the BOTTOM of the
            // library list pane. Narrows the rows currently shown client-side
            // (binds `searchText`, which drives `filteredDocuments`) — distinct
            // from the toolbar `.searchable`, which fires a *global* search.
            // Revealed on demand by ⌘F / the toolbar filter toggle, matching
            // Xcode's navigator filter field.
            .safeAreaInset(edge: .bottom, spacing: 0) {
                bottomInsetContent
            }
            .background(
                Group {
                    if featureManager.isLibraryFilterToolbarEnabled {
                        Button("") {
                            showFilterBar = true
                            filterFieldFocused = true
                        }
                        .keyboardShortcut("f", modifiers: .command)
                        .hidden()
                    }
                }
            )
            .sheet(isPresented: $showWorkflowPicker) {
                WorkflowPickerSheet(
                    selectedDocumentIds: selectedDocumentIdsForBatch,
                    onSelect: { workflowId in
                        Task { @MainActor in
                            await runBatchWorkflow(workflowId: workflowId)
                        }
                    }
                )
                .environment(libraryManager)
                .environment(executionObserver)
            }
            .sheet(item: $workspacePickerDocument) { document in
                WorkspaceItemPicker(document: document)
                    .environment(executionObserver)
            }
            .sheet(item: $bookmarkPickerDocument) { document in
                BookmarksView(document: document, onOpen: { openDocument($0) })
            }
            .focusedSceneValue(\.runWorkflowOnSelection, runWorkflowOnSelectionAction)
            .onAppear {
                if outlineModel == nil {
                    outlineModel = LibraryOutlineModel(
                        service: entityService,
                        artifactService: artifactService
                    )
                }
                // Mode-specific caches only when their view is the one shown on
                // appear (#3867/#3870); switching in later re-syncs via
                // onChange(displayMode). refreshLibraryProjection self-gates.
                if displayMode == .table { syncPagesByParentId() }
                loadSortSettings(for: folderId)
                syncSortOrder()
                recomputeFiltered()
                refreshLibraryProjection()
                consumePendingOpen()
            }
            // Merged the two former documentStore.revision observers into one
            // (#3870) — SwiftUI would run both every revision.
            .onChange(of: documentStore.revision) { _, _ in
                // Pending-open hand-off retry once rows arrive (#1685).
                recomputeFiltered()
                refreshLibraryProjection()               // no-op unless canvas/space (#3867)
                if displayMode == .table { syncPagesByParentId() }  // outline-only (#3870)
                consumePendingOpen()
            }
            // Recompute mode-specific caches lazily on switch-in, since the
            // per-revision paths now skip them off-mode (#3867 / #3870).
            .onChange(of: displayMode) { _, _ in
                refreshLibraryProjection()
                if displayMode == .table { syncPagesByParentId() }
            }
            .onChange(of: entities) { _, _ in
                recomputeFiltered()
                refreshLibraryProjection()
            }
            .onChange(of: scopedLibraryReference?.activityStore.refreshToken ?? 0) { _, _ in
                refreshPendingStatusesFromLiveUpdate()
            }
            .onChange(of: scopedLibraryReference?.activityStore.backendWork) { _, _ in
                refreshPendingStatusesFromLiveUpdate()
            }
            // Debounce ⌘F keystrokes (#3865): `.task(id:)` cancels the pending
            // task per keystroke → filter runs once after a ~200ms pause, not per
            // key. Empty query (clear) applies instantly; reuses the current index.
            .task(id: searchText) {
                if !searchText.isEmpty {
                    try? await Task.sleep(for: .milliseconds(200))
                    if Task.isCancelled { return }
                }
                recomputeFiltered(rebuildIndex: false)
            }
            .onChange(of: folderId) { _, newId in
                loadSortSettings(for: newId)
                syncSortOrder()
                recomputeFiltered()
            }
            .onChange(of: sortFieldRaw) { _, _ in
                syncSortOrder()
                saveSortSettings(for: folderId)
                recomputeFiltered()
            }
            .onChange(of: sortAscending) { _, _ in
                syncSortOrder()
                saveSortSettings(for: folderId)
                recomputeFiltered()
            }
            .onChange(of: sortOrder) { _, newOrder in
                handleSortOrderChange(newOrder)
                recomputeFiltered()
            }
            .onReceive(processingPollTimer) { _ in
                guard shouldUseProcessingPollFallback else { return }
                refreshPendingStatusesFromLiveUpdate()
            }
            .task(id: entityCollectionTaskKey) {
                await loadEntitiesIfNeeded()
            }
            // Suppress implicit animations on folder change — icons should appear
            // instantly, not slide in cascading from the top.
            .transaction(value: folderId) { $0.animation = nil }
        )
        // No toolbar .searchable here — ContentView owns the single GLOBAL
        // toolbar search (files), which already routes to runToolbarSearch. A
        // second .searchable in this window is a duplicate com.apple.SwiftUI.search
        // and can crash the macOS toolbar (#3163). The inline ⌘F filter stays.
    }
}

// MARK: - Connection error + bottom inset (#3160: kept out of the type body)
extension LibraryView {
    // Sort field / direction / filter-bar visibility now live on the shared
    // store (#1477). These computed forwarders keep the existing call sites and
    // `$`-bindings working unchanged.
    var sortFieldRaw: String {
        get { libraryToolbar.sortFieldRaw }
        nonmutating set { libraryToolbar.sortFieldRaw = newValue }
    }

    var sortAscending: Bool {
        get { libraryToolbar.sortAscending }
        nonmutating set { libraryToolbar.sortAscending = newValue }
    }

    var showFilterBar: Bool {
        get { libraryToolbar.showFilterBar }
        nonmutating set { libraryToolbar.showFilterBar = newValue }
    }

    var sortField: LibrarySortField { libraryToolbar.sortField }

    // internal (not private): accessed from LibraryView+DisplayModes extension (separate file)
    var scopedLibraryReference: LibraryManager.LibraryReference? {
        libraryManager.getLibrary(id: windowState.libraryId)
    }

    private var libraryReference: LibraryManager.LibraryReference? {
        libraryManager.getLibrary(id: windowState.libraryId) ?? libraryManager.globalLibrary
    }

    /// Canvas stores are shared per library (#3082), but must never silently
    /// swap to another library's client/scope while this window's library is
    /// still loading or unavailable (#3198).
    private var canvasLayoutStore: CanvasLayoutStore? { scopedLibraryReference?.canvasLayoutStore }
    private var canvasItemStore: CanvasItemStore? { scopedLibraryReference?.canvasItemStore }

    /// Extracted from `.focusedSceneValue` so the Swift type-checker doesn't
    /// time out on the inline ternary-with-closure expression.
    private var runWorkflowOnSelectionAction: (() -> Void)? {
        guard !isShowingEntitiesCollection, !selection.isEmpty,
              featureManager.isWorkflowRunOnSelectionEnabled else { return nil }
        return {
            selectedDocumentIdsForBatch = Array(selection)
            showWorkflowPicker = true
        }
    }

    private func refreshPendingStatusesFromLiveUpdate() {
        guard hasProcessingDocuments, let parentId = folderId else { return }
        Task { await documentStore.refreshPendingStatusesOnly(in: parentId) }
    }

    /// Shown only for a load that failed because the engine was unreachable
    /// (`isEngineOutage`) — never for a library that simply hasn't loaded yet.
    /// The engine is started and managed by the app, so the copy never asks the
    /// user to go check a service or a port they don't run.
    private var connectionErrorState: some View {
        VStack(spacing: 16) {
            Image(systemName: "wifi.slash")
                .font(.system(size: 48))
                .foregroundColor(.secondary)

            Text("Can't Reach the Engine")
                .font(.title2)
                .fontWeight(.semibold)
                // #3937's assertion target: this claims an outage, so a UI test
                // has to be able to catch it claiming one on a healthy engine.
                .accessibilityIdentifier("library.outage")

            Text("Fichero can't reach its engine right now, so this library can't load. Try again in a moment.")
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 400)

            Button("Try Again") {
                onRetry()
            }
            .keyboardShortcut("r", modifiers: .command)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    /// Filter bar + bottom action bar stacked at the bottom of every library view mode.
    private var bottomInsetContent: some View {
        VStack(spacing: 0) {
            if featureManager.isLibraryFilterToolbarEnabled && showFilterBar {
                filterBarView
            }
            libraryBottomActionBar
        }
    }
}

// MARK: - Bottom Action Bar (#2313)
extension LibraryView {
    private var bottomBarLogger: Logger {
        Logger(subsystem: "app.fichero.fichero", category: "LibraryView.BottomBar")
    }

    /// Minimum hit-target side for each bottom-bar button. Follows the shared
    /// MiniToolbar metric policy: 28pt on the Mac (compact Finder bar) but 44pt
    /// on touch platforms so iPhone/iPad targets are comfortably tappable (#2474).
    private var bottomBarTouchTarget: CGFloat {
        MiniToolbar<EmptyView, EmptyView>.touchTargetSide
    }

    /// Height of the bottom action bar. Matches the shared mini-toolbar policy
    /// so library, sidebar, reader, preview, and inspector strips line up.
    private var bottomBarHeight: CGFloat {
        MiniToolbar<EmptyView, EmptyView>.standardHeight
    }

    /// Finder/Xcode-style bottom toolbar acting on the current library selection.
    ///
    /// Rewrapped on the shared `AdaptiveMiniToolbarRow` (#3057, parent #2670) so
    /// the bar no longer "extends and is weird" in a narrow pane: essential verbs
    /// stay inline, secondary verbs collapse into a trailing `…` menu when they
    /// don't fit (macOS) or on compact width (iPhone). Every action / `.help` /
    /// `.accessibilityLabel` is unchanged — iterate, never replace.
    private var libraryBottomActionBar: some View {
        VStack(spacing: 0) {
            Divider()

            // Translucent Liquid Glass background, matching the sidebar mini-toolbars
            // (SidebarModeBar / SidebarBottomToolbar / PaneFilterBar) for a consistent
            // glass look across the window chrome (#2550).
            GlassEffectContainer {
                AdaptiveMiniToolbarRow {
                    essentialBarButtons
                } secondary: {
                    secondaryBarButtons
                } overflowMenu: {
                    bottomBarOverflowMenu
                }
                .padding(.horizontal, 10)
                .frame(height: bottomBarHeight)
                .glassEffect(.regular, in: RoundedRectangle(cornerRadius: 8))
            }
        }
    }

    /// Essential verbs — always inline (#3057): New Folder, Delete, Import. The
    /// trailing Spacer keeps them left-aligned with the secondary/overflow on the
    /// right, preserving the bar's existing Finder-style layout.
    @ViewBuilder
    private var essentialBarButtons: some View {
        Button {
            handleCreateNewFolder()
        } label: {
            Image(systemName: "plus")
                .accessibilityLabel("New Folder")
        }
        .buttonStyle(.borderless)
        .controlSize(.small)
        .frame(minWidth: bottomBarTouchTarget, minHeight: bottomBarTouchTarget)
        .contentShape(Rectangle())
        .help("Create a new folder")

        Button {
            promptDeleteSelected()
        } label: {
            Image(systemName: "minus")
                .accessibilityLabel("Delete")
        }
        .buttonStyle(.borderless)
        .controlSize(.small)
        .frame(minWidth: bottomBarTouchTarget, minHeight: bottomBarTouchTarget)
        .contentShape(Rectangle())
        .help("Delete selection")
        .disabled(isShowingEntitiesCollection || selection.isEmpty)

        Button {
            showingFileImporter = true
        } label: {
            Image(systemName: "square.and.arrow.down")
                .accessibilityLabel("Import")
        }
        .buttonStyle(.borderless)
        .controlSize(.small)
        .frame(minWidth: bottomBarTouchTarget, minHeight: bottomBarTouchTarget)
        .contentShape(Rectangle())
        .help("Import files")

        Spacer()
    }

    /// Secondary verbs — inline on Mac when they fit, else the `…` menu; menu-only
    /// on compact (#3057): entity filter (list mode), Export BibTeX, Run Workflow.
    @ViewBuilder
    private var secondaryBarButtons: some View {
        if displayMode == .list {
            entityFilterMenu
        }

        Button {
            Task { await exportSelectedBibtex() }
        } label: {
            Image(systemName: "square.and.arrow.up")
                .accessibilityLabel("Export BibTeX")
        }
        .buttonStyle(.borderless)
        .controlSize(.small)
        .frame(minWidth: bottomBarTouchTarget, minHeight: bottomBarTouchTarget)
        .contentShape(Rectangle())
        .help("Export selection as BibTeX")
        .disabled(isShowingEntitiesCollection || selection.isEmpty)

        Button {
            selectedDocumentIdsForBatch = Array(selection)
            showWorkflowPicker = true
        } label: {
            Image(systemName: "bolt")
                .accessibilityLabel("Run Workflow")
        }
        .buttonStyle(.borderless)
        .controlSize(.small)
        .frame(minWidth: bottomBarTouchTarget, minHeight: bottomBarTouchTarget)
        .contentShape(Rectangle())
        .help("Run workflow on selection")
        .disabled(isShowingEntitiesCollection || selection.isEmpty || !featureManager.isWorkflowRunOnSelectionEnabled)
    }

    /// `Label`-based mirror of the secondary verbs for the overflow `…` menu
    /// (#3057) — same actions + disabled logic, menu-item presentation.
    @ViewBuilder
    private var bottomBarOverflowMenu: some View {
        if displayMode == .list {
            entityFilterMenu
        }

        Button {
            Task { await exportSelectedBibtex() }
        } label: {
            Label("Export BibTeX", systemImage: "square.and.arrow.up")
        }
        .disabled(isShowingEntitiesCollection || selection.isEmpty)

        Button {
            selectedDocumentIdsForBatch = Array(selection)
            showWorkflowPicker = true
        } label: {
            Label("Run Workflow", systemImage: "bolt")
        }
        .disabled(isShowingEntitiesCollection || selection.isEmpty || !featureManager.isWorkflowRunOnSelectionEnabled)
    }

    private func exportSelectedBibtex() async {
        guard !selection.isEmpty else { return }
        let documentIds = Array(selection)
        guard let library = libraryManager.getLibrary(id: windowState.libraryId) else { return }

        do {
            // Route through the service wrapper instead of raw ficheroClient.api
            // (observable-data-layer, #3258); it owns the response handling.
            let bib = try await library.entityService.exportBibliographyBib(documentIds: documentIds)
            guard let saveURL = await presentBibtexSavePanel() else { return }
            try Data(bib.utf8).write(to: saveURL, options: .atomic)
        } catch {
            bottomBarLogger.error("Failed to export selected BibTeX: \(error.localizedDescription)")
        }
    }

    private func presentBibtexSavePanel() async -> URL? {
        #if canImport(AppKit)
        await withCheckedContinuation { continuation in
            let savePanel = NSSavePanel()
            savePanel.nameFieldStringValue = "selection.bib"
            if let bibType = UTType(filenameExtension: "bib") {
                savePanel.allowedContentTypes = [bibType]
            }
            savePanel.allowsOtherFileTypes = false
            savePanel.canCreateDirectories = true
            savePanel.begin { result in
                continuation.resume(returning: result == .OK ? savePanel.url : nil)
            }
        }
        #else
        return nil
        #endif
    }

    private func handleCreateNewFolder() {
        guard libraryManager.globalLibrary != nil else { return }
        // Creation lives on the library's document store; no sidebarState here.
        Task {
            guard let library = libraryManager.getLibrary(id: windowState.libraryId)
                ?? libraryManager.globalLibrary else { return }
            do {
                _ = try await library.documentStore.createCollection(name: "New Folder")
                await library.documentStore.refresh()
            } catch {
                bottomBarLogger.error("Failed to create folder from bottom bar: \(error.localizedDescription)")
            }
        }
    }

    private func handleBottomBarImport(_ result: Result<[URL], Error>) {
        switch result {
        case .success(let urls):
            Task { @MainActor in
                guard let library = libraryManager.getLibrary(id: windowState.libraryId)
                    ?? libraryManager.globalLibrary else { return }
                do {
                    _ = try await library.importService.importFiles(urls, mode: .link)
                    await library.documentStore.refresh()
                } catch {
                    bottomBarLogger.error("Bottom-bar import failed: \(error.localizedDescription)")
                }
            }
        case .failure(let error):
            bottomBarLogger.debug("Bottom-bar import cancelled or failed: \(error.localizedDescription)")
        }
    }

}

// MARK: - Spatial projection

extension LibraryView {
    /// The spatial projection only feeds the `.canvas` / `.space` canvases, so
    /// mapping every document + entity through `SpatialLibraryProjector` on each
    /// documentStore/entity change is wasted work in icon/list/table (#3867).
    static func usesSpatialProjection(_ mode: ViewDisplayMode) -> Bool {
        switch mode {
        case .canvas, .space, .workspace: return true
        case .icon, .list, .table: return false
        }
    }

    private func refreshLibraryProjection() {
        // Skip the full documents+entities map unless a spatial canvas is shown.
        // Recomputed lazily on switch INTO canvas/space (see onChange(displayMode)).
        guard Self.usesSpatialProjection(displayMode) else { return }
        cachedLibraryProjection = SpatialLibraryProjector.project(
            SpatialLibraryInput(
                documents: documents.map {
                    SpatialLibraryInput.Document(id: $0.id, name: $0.name, parentId: $0.parentId)
                },
                entities: entities.compactMap { entity in
                    guard let id = entity.id else { return nil }
                    return SpatialLibraryInput.Entity(
                        id: id,
                        canonicalName: entity.canonicalName,
                        entityType: entity.entityType?.rawValue
                    )
                },
                claims: []
            )
        )
    }

    /// Projects the current documents + entities into spatial nodes/links for
    /// the `.canvas` (and future `.space`) views. Item positions are persisted
    /// separately via `CanvasLayoutStore` (#2293); this only supplies the
    /// projector's computed defaults.
    var libraryProjection: SpatialLibraryProjection {
        cachedLibraryProjection
    }
}

// MARK: - Kept out of the type body (type_body_length, mirrors #3160)

private extension LibraryView {
    // Processing poller (#518): if any visible docs are still processing, keep
    // a lightweight 15s refresh running so statuses advance to completed even
    // if a backend completion signal is missed.
    private var hasProcessingDocuments: Bool {
        documents.contains { $0.status == .processing || $0.status == .pending }
    }

    /// Spatial node ids of container documents (folder / workspace) — drag-onto
    /// move-into targets (#3086). Dropping onto one moves the dragged doc inside.
    private var canvasContainerIds: Set<String> {
        Set(
            documentStore.collections
                .filter { $0.docType == .folder || $0.isWorkspace }
                .map { SpatialLibraryProjector.nodeId(forDocument: $0.id) }
        )
    }
}

// MARK: - Previews

#Preview("Empty") {
    let client = FicheroClient(libraryPath: nil)
    LibraryView(
        documents: [],
        contentCollection: .documents,
        isLoading: false,
        isConnected: true,
        errorMessage: nil,
        onRetry: {},
        libraryToolbar: LibraryToolbarState(),
        selection: .constant(Set<String>()),
        detailDocument: .constant(nil),
        viewMode: .constant(.icons),
        displayMode: .icon,
        folderId: nil
    )
    .environment(ArtifactService(ficheroClient: client))
    .frame(width: 600, height: 500)
}

#Preview("Disconnected") {
    let client = FicheroClient(libraryPath: nil)
    LibraryView(
        documents: [],
        contentCollection: .documents,
        isLoading: false,
        isConnected: false,
        errorMessage: nil,
        onRetry: {},
        libraryToolbar: LibraryToolbarState(),
        selection: .constant(Set<String>()),
        detailDocument: .constant(nil),
        viewMode: .constant(.icons),
        displayMode: .icon,
        folderId: nil
    )
    .environment(ArtifactService(ficheroClient: client))
    .frame(width: 600, height: 500)
}
