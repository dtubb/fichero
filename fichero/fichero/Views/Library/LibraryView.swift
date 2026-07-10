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
    /// Bottom-bar file import presenter (#2313).
    @State var showingFileImporter = false
    @FocusState var filterFieldFocused: Bool
    @State var sortOrder: [KeyPathComparator<Document>] = [.init(\.name, order: .forward)]
    @SceneStorage("library.sortFieldsByFolder") var sortFieldsByFolderJSON: String = "{}"
    @SceneStorage("library.sortAscendingByFolder") var sortAscendingByFolderJSON: String = "{}"

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

    var sortField: LibrarySortField {
        libraryToolbar.sortField
    }

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
    @Environment(EntityServiceGenerated.self) var entityService
    @Environment(ArtifactServiceGenerated.self) var artifactService
    @Environment(WorkflowExecutionObserver.self) var executionObserver
    @Environment(KGFocusState.self) var kgFocusState
    @ObservedObject var featureManager = FeatureManager.shared
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

    @State var isLoadingEntities = false
    @State var entityLoadErrorMessage: String?

    // ponytail: recompute inputs — documents, entities, searchText, sortOrder, sortFieldRaw, sortAscending, folderId
    // Not `private`: recomputeFiltered() lives in the LibraryView+FilterAndBatch.swift
    // extension (a different file), so these must be at least internal to be visible there.
    @State var filteredDocuments: [Document] = []
    @State var filteredEntities: [Components.Schemas.KnowledgeEntity] = []
    /// Stable key for .task(id:) in iconsView — updated inside recomputeFiltered()
    /// to reset thumbnail prefetch state when the visible document set changes.
    @State var thumbnailPrefetchKey: String = ""
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
    private var hasProcessingDocuments: Bool {
        documents.contains { $0.status == .processing || $0.status == .pending }
    }
    private var shouldUseProcessingPollFallback: Bool {
        guard let ref = scopedLibraryReference else { return false }
        return ref.changeStream.liveUpdatesUnavailable || ref.activityStore.liveUpdatesPaused
    }

    // Extracted from `body` to keep the body modifier chain within the Swift
    // type-checker's budget — adding the #2307 onChange handlers tipped the
    // single expression over "unable to type-check in reasonable time".
    // See memory: librarywindow-body-typecheck-timeout.
    @ViewBuilder
    private var libraryContent: some View {
        if !isConnected {
            connectionErrorState
        } else if isCollectionLoading {
            loadingState
        } else if !isShowingEntitiesCollection, let denial = AccessError.from(documentStore.error) {
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

    /// The 3D Space renderer, gated (#3104): the new contract-based
    /// `CanvasSpaceView` when the flag is on, else the #3088 `SpaceSceneView`.
    /// Both read the SAME shared stores; #3088 stays the stepping-stone until
    /// cutover (#3087). Extracted to keep `libraryContent`'s switch bounded.
    /// Spatial node ids of container documents (folder / workspace) — drag-onto
    /// move-into targets (#3086). Dropping onto one moves the dragged doc inside.
    private var canvasContainerIds: Set<String> {
        Set(
            documentStore.collections
                .filter { $0.docType == .folder || $0.isWorkspace }
                .map { SpatialLibraryProjector.nodeId(forDocument: $0.id) }
        )
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
                syncPagesByParentId()
                loadSortSettings(for: folderId)
                syncSortOrder()
                recomputeFiltered()
                refreshLibraryProjection()
                consumePendingOpen()
            }
            .onChange(of: documentStore.revision) { _, _ in
                // A window opened via "Open in New Tab/Window" may still be
                // loading its documents when it first appears; retry the
                // pending-open hand-off once rows arrive (#1685).
                recomputeFiltered()
                refreshLibraryProjection()
                consumePendingOpen()
            }
            .onChange(of: documentStore.revision) { _, _ in
                syncPagesByParentId()
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
            .onChange(of: searchText) { _, _ in
                recomputeFiltered()
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
    private func refreshPendingStatusesFromLiveUpdate() {
        guard hasProcessingDocuments, let parentId = folderId else { return }
        Task { await documentStore.refreshPendingStatusesOnly(in: parentId) }
    }

    private var connectionErrorState: some View {
        VStack(spacing: 16) {
            Image(systemName: "wifi.slash")
                .font(.system(size: 48))
                .foregroundColor(.secondary)

            Text("Backend Not Connected")
                .font(.title2)
                .fontWeight(.semibold)

            Text("The Fichero backend is not responding. Make sure the server is running on port 8765.")
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 400)

            Button("Retry Connection") {
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

    /// Height of the bottom action bar. Stays compact (28pt) on the Mac and
    /// grows to the standard touch height on iPhone/iPad so the larger hit
    /// targets fit (#2474).
    private var bottomBarHeight: CGFloat {
        #if os(macOS)
        return 28
        #else
        return MiniToolbar<EmptyView, EmptyView>.standardHeight
        #endif
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
    private func refreshLibraryProjection() {
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
    .environment(ArtifactServiceGenerated(ficheroClient: client))
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
    .environment(ArtifactServiceGenerated(ficheroClient: client))
    .frame(width: 600, height: 500)
}
