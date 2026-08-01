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
    /// Sidebar-parity Add to Chat (#4121): the host opens chat scoped to the
    /// current selection; nil hides the menu item (previews, non-chat hosts).
    var onAddToChat: (() -> Void)?
    /// The engine-search field's text and mode, now that the field lives in
    /// the library's own mini toolbar rather than on the window (#4407).
    /// Defaulted so the previews construct unchanged.
    var searchFieldText: Binding<String> = .constant("")
    var searchFieldMode: Binding<SearchFieldMode> = .constant(.ask)
    /// The transient search this grid is showing results for, if any (#4403).
    /// Non-nil means the empty state must talk about the SEARCH — never about
    /// choosing a collection, which is what it used to fall back to under a
    /// header reading "3 results for …".
    var activeSearchQuery: String?
    /// What that search matched, per kind. The grid can only render the
    /// document leg, so these are how the body explains a header count it
    /// cannot show.
    var searchHitCounts: SearchHitCounts = SearchHitCounts()

    @State var searchText: String = ""
    /// Precomputed lowercased ⌘F search keys per docId (#3865). Rebuilt only when
    /// the document set changes, so keystroke filtering is a dict lookup, not a
    /// fresh full-OCR scan. See `rebuildDocumentSearchKeys`.
    @State var documentSearchKeys: [String: String] = [:]
    /// The ONE file-picker presenter every import affordance shares (#4449):
    /// the bottom-bar Import button, and the folder contextual-menu "Import
    /// Here…" item. Originally #2313 for just the bottom bar.
    @State var showingFileImporter = false
    /// The container the in-flight `showingFileImporter` picker imports into.
    /// Set immediately before flipping `showingFileImporter = true` so every
    /// presenter states its own target explicitly — nil silently lands
    /// documents at the library root, which is the "+ on a folder imports to
    /// the root" bug this issue exists to close (#4449).
    @State var fileImportTargetFolderId: String?
    /// Link/Copy/Move for the in-flight `showingFileImporter` picker (#4452)
    /// — the Data-menu Import submenu offers all three; the bottom-bar and
    /// contextual-menu affordances always want `.link` and set this
    /// explicitly rather than relying on the default.
    @State var fileImportMode: IngestMode = .link
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
    /// any column header → show/hide menu, drag to reorder, drag-resize).
    /// Backed by SwiftUI's TableColumnCustomization API. Persisted via
    /// @SceneStorage (the follow-up the old @State comment promised, #519/
    /// #4160): resize/reorder/show-hide now survive relaunch, per window —
    /// matching how sort already persists.
    @SceneStorage("library.tableColumns")
    var tableColumnCustomization: TableColumnCustomization<LibraryOutlineNode> = .init()

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
    // Canvas/spatial selection is NOT separate state: it is `selection`,
    // translated through `canvasSelectedNodeIds` (#4192, widened by #4409).
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
    // #4198: delete acts on document rows and states what it skips; a
    // child-only selection presents the same dialog as a plain notice
    // instead of a silent no-op.
    @State var deleteSkippedNote: String?

    // Inline rename state
    @State var renamingDocumentId: String?
    @State var editingName: String = ""

    // Miller columns (#4160 step 4): the folder-ID chain below the browsed
    // root (ids, never Document snapshots — every segment resolves through
    // the live children cache each render and truncates when one dies), the
    // active column depth, and the per-folder children cache the column
    // stack's .task fills through DocumentStore.children(of:).
    @State var columnsPath: [String] = []
    @State var columnsActiveDepth: Int = 0
    @State var columnsChildren: [String: [Document]] = [:]

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
    // Keyboard cursor (#4160): the row arrow-nav last landed on. The old code
    // used `selection.first` — Set hash order — so after a multi-select the
    // arrows resumed from, Return opened, and the list scrolled to an
    // arbitrary row.
    @State var selectionCursor: String?
    // Space → Quick Look temp-file URL (#4160); non-nil presents the panel.
    @State var quickLookURL: URL?

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
    /// `ConnectionPresentation.failureTitle` is pure (#3341).
    /// `nonisolated` is LOAD-BEARING: a static on a `View` inherits the type's
    /// MainActor isolation under the macOS 26 SDK, and the Swift Testing suite
    /// that calls this runs on a cooperative thread — the off-main call
    /// SIGTRAPs the whole test process, nondeterministically and misattributed
    /// to whichever test happened to be running (#4201).
    nonisolated static func isAwaitingFirstLoad(hasLoadedSuccessfully: Bool, error: Error?) -> Bool {
        !hasLoadedSuccessfully && error == nil
    }

    /// True only when a load failed because the engine could not be REACHED
    /// (#3937) — the one state that earns the outage pane. Every other failure
    /// keeps its own message via `errorState`, and no failure at all is not an
    /// outage. Reuses the one `AccessError` classifier instead of re-reading
    /// `URLError` codes here. An already-typed `AccessError` never arrives: the
    /// access-denied branch above claims it first.
    /// `nonisolated` for the same load-bearing reason as `isAwaitingFirstLoad`
    /// above — and it must stay that way transitively: everything this reads
    /// (`AccessError.classify`) has to be callable off-main too (#4201).
    nonisolated static func isEngineOutage(_ error: Error?) -> Bool {
        guard let error else { return false }
        return AccessError.classify(error) == .engineUnreachable
    }

    // Extracted from `body` to keep the body modifier chain within the Swift
    // type-checker's budget — adding the #2307 onChange handlers tipped the
    // single expression over "unable to type-check in reasonable time".
    // See memory: librarywindow-body-typecheck-timeout.
    @ViewBuilder
    private var libraryContent: some View {
        // #4372: a failed engine is an error affordance, never a spinner. This
        // branch has to come FIRST, because `isAwaitingFirstLoad` is true
        // whenever no load has succeeded AND no load has failed — which is
        // exactly the shape of "the engine never answered, so nothing was ever
        // asked for". Without it the pane spins forever over a dead engine.
        if let engineFailure = engineFailureDetail {
            connectionErrorState(message: engineFailure)
        } else if isCollectionLoading || isAwaitingFirstLoad {
            loadingState
        } else {
            libraryFailureOrRows
        }
    }

    /// The failure branches, split out of `libraryContent` so no single
    /// `@ViewBuilder` body carries seven branches plus a nested switch.
    ///
    /// Purely a factoring: the chain order is unchanged, so the precedence
    /// (access denial → engine outage → generic error → rows) is exactly what
    /// it was. `LibraryWindow.body` has a documented type-check-timeout history
    /// in this codebase and #4372 added a branch to this chain, so it is
    /// bounded now rather than after a failed build.
    @ViewBuilder
    private var libraryFailureOrRows: some View {
        if !isShowingEntitiesCollection, let denial = documentStore.error as? AccessError {
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
            connectionErrorState(message: engineUnreachableDetail)
        } else if let activeErrorMessage {
            errorState(message: activeErrorMessage)
        } else {
            libraryRowsOrEmptyState
        }
    }

    /// The final answer: rows, or the empty/placeholder state.
    @ViewBuilder
    private var libraryRowsOrEmptyState: some View {
        if isCollectionEmpty {
            // "Empty folder" and "contents not here yet" looked identical, so a
            // folder click or a drop showed "No Documents" and then relaid out
            // when the data landed (#4235). Show what is already in flight.
            let placeholder = emptyCollectionPlaceholder
            if placeholder == .empty {
                emptyState
            } else {
                contentPlaceholderState(placeholder)
            }
        } else {
            switch displayMode {
            case .icon:
                iconsView
            case .list:
                listView
            case .table:
                tableView
            case .columns:
                columnsView
            case .canvas, .workspace:
                canvasModeView
            case .space:
                spaceModeView
            }
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
            // The library's own mini toolbar (#4407 / #4374): search, sort and
            // filter live with the surface they act on. Top on the Mac, bottom
            // on touch — the same single platform decision the reader's find
            // bar makes, from the same place, so the two panes agree. Because
            // it is an inset on THIS view it resizes with the library pane and
            // disappears with it, which window chrome could never do.
            .safeAreaInset(edge: .top, spacing: 0) {
                if Self.miniToolbarPlacement == .top {
                    PaneFilterBar(placement: .top) { libraryMiniToolbar }
                }
            }
            // Closes the sidebar-click interval opened in `handleSelectionChange`
            // (#4228). See `InteractionProfile.Phase.selectionToContent` for what
            // this end point does and does not measure.
            .task(id: folderId) { InteractionProfile.end(.selectionToContent, detail: folderId ?? "nil") }
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
            // Data-menu Import… while the LIBRARY pane (not the sidebar) has
            // focus (#4452). Deliberately the narrow `libraryImportAction`
            // key, not `sidebarActions` — see that key's doc comment for why
            // stubbing the other 10 SidebarActions closures would be a new
            // silent no-op bug of the exact shape #4449 just closed.
            .focusedValue(\.libraryImportAction) { mode in
                fileImportMode = mode
                fileImportTargetFolderId = folderId
                showingFileImporter = true
            }
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
            .onChange(of: showFilterBar) { _, shown in filterBarVisibilityChanged(shown) }
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
    /// Promoted `private` → internal: read from `LibraryView+CanvasModes.swift`
    /// after the #4353 file split, and `private` is file-scoped.
    var canvasLayoutStore: CanvasLayoutStore? { scopedLibraryReference?.canvasLayoutStore }
    var canvasItemStore: CanvasItemStore? { scopedLibraryReference?.canvasItemStore }

    /// Extracted from `.focusedSceneValue` so the Swift type-checker doesn't
    /// time out on the inline ternary-with-closure expression. Wrapped in
    /// `FocusedLibraryAction` (Equatable, keyed on `isEnabled` only) so the
    /// focus system short-circuits across body passes — publishing a raw
    /// closure here caused an AttributeGraph invalidation storm on launch
    /// whenever a persisted selection restored (hang / AG compare crash).
    private var runWorkflowOnSelectionAction: FocusedLibraryAction? {
        guard !isShowingEntitiesCollection, !selection.isEmpty,
              featureManager.isWorkflowRunOnSelectionEnabled else { return nil }
        return FocusedLibraryAction(isEnabled: true) {
            selectedDocumentIdsForBatch = Array(selection)
            showWorkflowPicker = true
        }
    }

    private func refreshPendingStatusesFromLiveUpdate() {
        guard hasProcessingDocuments, let parentId = folderId else { return }
        Task { await documentStore.refreshPendingStatusesOnly(in: parentId) }
    }

    /// Shown for a load that failed because the engine was unreachable
    /// (`isEngineOutage`) or because the engine itself is in a failure phase —
    /// never for a library that simply hasn't loaded yet.
    ///
    /// The sentence comes from `ConnectionPresentation` (#4380), the same
    /// mapping the engine popover reads, so the two surfaces cannot describe
    /// one failure two different ways. A raw transport error never reaches
    /// this pane (#4269); it lives in the engine log.
    private func connectionErrorState(message: String) -> some View {
        VStack(spacing: 16) {
            Image(systemName: "wifi.slash")
                .font(.largeTitle)
                .foregroundColor(.secondary)

            Text("Can't Reach the Server")
                .font(.title2)
                .fontWeight(.semibold)
                // #3937's assertion target: this claims an outage, so a UI test
                // has to be able to catch it claiming one on a healthy engine.
                .accessibilityIdentifier("library.outage")

            Text(message)
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

    /// The honest sentence for the CURRENT engine phase, or nil when the engine
    /// is not in a failure phase at all (#4372). Non-nil is what promotes the
    /// pane from "loading" to "the error affordance".
    private var engineFailureDetail: String? {
        switch appState.engine.phase {
        case .portConflict, .authRejected, .unreachable, .failed:
            return engineStatusDetail
        case .setupNeeded, .starting, .ready:
            return nil
        }
    }

    /// The sentence for a store load that failed with `engineUnreachable` while
    /// the session itself has not (yet) flipped to a failure phase.
    private var engineUnreachableDetail: String {
        ConnectionPresentation.failureDetail(
            accessError: .engineUnreachable,
            authBroken: false,
            ownership: ConnectionPresentation.EngineOwnership.current()
        )
    }

    /// Everything stacked below the library's rows, in ONE inset with an
    /// explicit order (#4424).
    ///
    /// It used to be two separate `.safeAreaInset(edge: .bottom)` modifiers —
    /// the mini toolbar added by #4407, then this one. SwiftUI applies insets
    /// outward in modifier order, so the later one lands FURTHEST from the
    /// content: the window-scoped status row ended up beneath the pane-scoped
    /// mini toolbar, which says the opposite of what is true about their
    /// scopes. Two bottom insets is two orderings competing; one inset with a
    /// stated order cannot drift.
    ///
    /// Order, content outward:
    ///   1. the library's mini toolbar — pane-scoped, so nearest its rows
    ///   2. the quick-filter row it reveals
    ///   3. the bottom action/status bar — the outermost thing, beneath all of it
    private var bottomInsetContent: some View {
        VStack(spacing: 0) {
            if Self.miniToolbarPlacement == .bottom {
                PaneFilterBar(placement: .bottom) { libraryMiniToolbar }
            }
            if featureManager.isLibraryFilterToolbarEnabled && showFilterBar {
                filterBarView
            }
            libraryBottomActionBar
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
        case .icon, .list, .table, .columns: return false
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

}

// Moved OUT of the `private extension` above, not merely un-marked: a member's
// own access modifier cannot exceed its enclosing extension's, so dropping
// `private` from the property left it fileprivate and still unreachable from
// `LibraryView+CanvasModes.swift` after the #4353 split.
extension LibraryView {
    /// Spatial node ids of container documents (folder / workspace) — drag-onto
    /// move-into targets (#3086). Dropping onto one moves the dragged doc inside.
    var canvasContainerIds: Set<String> {
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
