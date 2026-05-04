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

    @State var searchText: String = ""
    @State var showFilterBar = false
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
    @Environment(WorkflowExecutionObserver.self) var executionObserver
    @ObservedObject var featureManager = FeatureManager.shared

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
    @State var listScrollTarget: String?

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
                    case .map:
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
            // Suppress implicit animations on folder change — icons should appear
            // instantly, not slide in cascading from the top.
            .transaction(value: folderId) { $0.animation = nil }
        )
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                // Filter button — opens inline filter bar (like Finder's filter strip)
                if featureManager.isLibraryFilterToolbarEnabled {
                    Button {
                        showFilterBar = true
                        filterFieldFocused = true
                    } label: {
                        Image(systemName: showFilterBar ? "line.3.horizontal.decrease.circle.fill"
                                : "line.3.horizontal.decrease.circle")
                    }
                    .help("Filter (⌘F)")
                }

                // Zoom controls — icon and map views only
                if featureManager.isLibraryIconZoomControlsEnabled && (displayMode == .icon || displayMode == .map) {
                    Button {
                        if displayMode == .icon {
                            iconViewScale = max(0.5, iconViewScale - 0.25)
                        } else {
                            mapCanvasScale = max(0.25, mapCanvasScale - 0.25)
                        }
                    } label: {
                        Image(systemName: "minus.magnifyingglass")
                    }
                    .help("Zoom Out (⌘-)")
                    .keyboardShortcut("-", modifiers: .command)

                    Button {
                        if displayMode == .icon { iconViewScale = 1.0 } else { mapCanvasScale = 1.0 }
                    } label: {
                        Image(systemName: "1.magnifyingglass")
                    }
                    .help("Reset Zoom")

                    Button {
                        // Raised from 3.0 → 5.0 so users can inspect
                        // fine detail (stamps, handwriting) without the
                        // zoom pegging too early (#604).
                        if displayMode == .icon {
                            iconViewScale = min(5.0, iconViewScale + 0.25)
                        } else {
                            mapCanvasScale = min(5.0, mapCanvasScale + 0.25)
                        }
                    } label: {
                        Image(systemName: "plus.magnifyingglass")
                    }
                    .help("Zoom In (⌘=)")
                    .keyboardShortcut("=", modifiers: .command)
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
