import Combine
import SwiftUI
import UniformTypeIdentifiers

/// Grid/List/Table/Map view of documents
struct LibraryView: View {
    let documents: [Document]
    let isLoading: Bool
    let isConnected: Bool
    let errorMessage: String?
    let onRetry: () -> Void
    @Binding var selection: Set<String>
    @Binding var detailDocument: Document?
    @Binding var viewMode: LibraryLayout
    let displayMode: ViewDisplayMode  // Universal view mode from toolbar

    let folderId: String?  // Current folder ID for per-folder sort persistence
    var onRequestFocus: () -> Void = {}  // Called on tap to pull keyboard focus into content area
    var onRequestPreviousPaneFocus: () -> Void = {}  // Left arrow in list/table — move to sidebar
    var onRequestNextPaneFocus: () -> Void = {}  // Right arrow in list/table — move to inspector
    var onNavigateInto: (Document) -> Void = { _ in }  // Double-click on folder/PDF — navigate into it
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
    @State var showFilterBar = false
    /// Text for the toolbar's `.searchable` field. Distinct from
    /// `searchText` (which drives the inline ⌘F filter bar inside the
    /// view) — `toolbarQuery` lives on the window toolbar so users can
    /// fire a *global* search from any folder context, while the
    /// inline filter stays as a quick local-narrow.
    @State var toolbarQuery: String = ""
    @FocusState var filterFieldFocused: Bool
    @State var sortFieldRaw: String = LibrarySortField.name.rawValue
    @State var sortAscending: Bool = true
    @State var sortOrder: [KeyPathComparator<Document>] = [.init(\.name, order: .forward)]
    @SceneStorage("library.sortFieldsByFolder") var sortFieldsByFolderJSON: String = "{}"
    @SceneStorage("library.sortAscendingByFolder") var sortAscendingByFolderJSON: String = "{}"

    var sortField: LibrarySortField {
        LibrarySortField(rawValue: sortFieldRaw) ?? .name
    }

    // Workflow picker state
    @State var showWorkflowPicker = false
    @State var selectedDocumentIdsForBatch: [String] = []

    @EnvironmentObject var libraryManager: LibraryManager
    @EnvironmentObject var windowState: WindowState
    @EnvironmentObject var workflowStreamService: WorkflowStreamService
    @EnvironmentObject var documentStore: DocumentStore
    @Environment(WorkflowExecutionObserver.self) var executionObserver
    @ObservedObject var featureManager = FeatureManager.shared
    @ObservedObject var workflowRunProviderCache = WorkflowRunProviderCache.shared

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
    @State var tableColumnCustomization = TableColumnCustomization<Document>()

    // Map view positions
    @State var mapPositions: [String: CGPoint] = [:]

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

    // Zoom scale for icon and map views (persisted per-app)
    @AppStorage("library.iconViewScale") var iconViewScale: Double = 1.0
    @State var mapCanvasScale: CGFloat = 1.0
    // Captures iconViewScale at the start of a pinch so the gesture's
    // multiplier multiplies against the gesture-start size, not the
    // continuously-updating scale (which would compound exponentially).
    @State var pinchBaseScale: Double = 1.0

    // Processing poller (#518): fires while any document is
    // pending/processing so the row indicator updates without manual refresh.
    // Auto-stops when all documents settle; the onRetry()-triggered fetch
    // updates `documents` which gates `hasProcessingDocuments` to false.
    //
    // 15s interval (was 3s) — 3s caused visible whole-list flash on libraries
    // with one stuck pending row, because onRetry() replaces the documents
    // array wholesale and SwiftUI re-renders every visible row. 15s gives
    // reasonable ingest feedback without the flicker. Once we wire SSE-based
    // status push (0.0.4 hybrid retrieval scope) the poll can go away entirely.
    private let processingPollTimer = Timer.publish(every: 15, on: .main, in: .common).autoconnect()
    private var hasProcessingDocuments: Bool {
        documents.contains { $0.status == .processing || $0.status == .pending }
    }

    var body: some View {
        withKeyboardShortcuts(
            VStack(spacing: 0) {
                // Inline filter bar (Cmd+F)
                if featureManager.isLibraryFilterToolbarEnabled && showFilterBar {
                    filterBarView
                }

                // Main content
                if !isConnected {
                    connectionErrorState
                } else if isLoading {
                    loadingState
                } else if let errorMessage {
                    errorState(message: errorMessage)
                } else if filteredDocuments.isEmpty {
                    emptyState
                } else {
                    switch displayMode {
                    case .icon:
                        iconsView
                    case .list:
                        listView
                    case .table:
                        tableView
                    case .map, .realitykit:
                        mapView
                    }
                }
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
                .environmentObject(libraryManager)
            }
            .focusedSceneValue(
                \.runWorkflowOnSelection,
                (!selection.isEmpty && featureManager.isWorkflowRunOnSelectionEnabled) ? {
                    selectedDocumentIdsForBatch = Array(selection)
                    showWorkflowPicker = true
                } : nil
            )
            .onAppear {
                loadSortSettings(for: folderId)
                syncSortOrder()
            }
            .onChange(of: folderId) { _, newId in
                loadSortSettings(for: newId)
                syncSortOrder()
            }
            .onChange(of: sortFieldRaw) { _, _ in
                syncSortOrder()
                saveSortSettings(for: folderId)
            }
            .onChange(of: sortAscending) { _, _ in
                syncSortOrder()
                saveSortSettings(for: folderId)
            }
            .onChange(of: sortOrder) { _, newOrder in
                handleSortOrderChange(newOrder)
            }
            .onReceive(processingPollTimer) { _ in
                // Surgical refresh: only mutate rows whose status changed
                // (#518 follow-up). The previous onRetry() path replaced
                // the whole documents array → SwiftUI re-rendered every
                // visible row → flash. refreshPendingStatusesOnly walks
                // currentDocuments in place and only swaps rows whose
                // status flipped, so untouched rows keep referential
                // identity and don't redraw.
                guard hasProcessingDocuments, let parentId = folderId else { return }
                Task { await documentStore.refreshPendingStatusesOnly(in: parentId) }
            }
            // Suppress implicit animations on folder change — icons should appear
            // instantly, not slide in cascading from the top.
            .transaction(value: folderId) { $0.animation = nil }
        )
        // Toolbar search field — Finder-style magnifying-glass that
        // expands when clicked, always visible while in library mode.
        // Submit fires onToolbarSearchSubmit (wired to runToolbarSearch
        // by ContentView), which switches the sidebar to .search mode.
        // Each mode owns its own .searchable to avoid the NSToolbar
        // duplicate-identifier crash we hit when stacking them.
        .searchable(
            text: $toolbarQuery,
            placement: .toolbar,
            prompt: "Search documents…"
        )
        .onSubmit(of: .search) {
            let trimmed = toolbarQuery.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty else { return }
            onToolbarSearchSubmit(trimmed)
        }
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                // Entity-type filter — toggles which People/Places/Orgs/
                // Dates/Events/Keywords lozenges show in list rows.
                // Hidden in non-list modes (icon/table/map) where no
                // lozenges are rendered, so the button's purpose is clear
                // (#1473 — Daniel: "not sure why this is here").
                if displayMode == .list {
                    entityFilterMenu
                }
            }
        }
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
}

// MARK: - Previews

#Preview("Empty") {
    LibraryView(
        documents: [],
        isLoading: false,
        isConnected: true,
        errorMessage: nil,
        onRetry: {},
        selection: .constant(Set<String>()),
        detailDocument: .constant(nil),
        viewMode: .constant(.icons),
        displayMode: .icon,
        folderId: nil
    )
    .frame(width: 600, height: 500)
}

#Preview("Disconnected") {
    LibraryView(
        documents: [],
        isLoading: false,
        isConnected: false,
        errorMessage: nil,
        onRetry: {},
        selection: .constant(Set<String>()),
        detailDocument: .constant(nil),
        viewMode: .constant(.icons),
        displayMode: .icon,
        folderId: nil
    )
    .frame(width: 600, height: 500)
}
