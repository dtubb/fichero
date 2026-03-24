import SwiftUI
import UniformTypeIdentifiers

/// Grid/List/Table/Map view of documents
struct LibraryView: View {
    let documents: [Document]
    @Binding var selection: Set<String>
    @Binding var detailDocument: Document?
    @Binding var viewMode: LibraryLayout
    let displayMode: ViewDisplayMode  // Universal view mode from toolbar

    let folderId: String?  // Current folder ID for per-folder sort persistence
    var onRequestFocus: () -> Void = {}  // Called on tap to pull keyboard focus into content area
    var onRequestPreviousPaneFocus: () -> Void = {}  // Left arrow in list/table — move to sidebar
    var onRequestNextPaneFocus: () -> Void = {}  // Right arrow in list/table — move to inspector

    @State var searchText: String = ""
    @State var showFilterBar = false
    @FocusState var filterFieldFocused: Bool
    @State var sortFieldRaw: String = LibrarySortField.name.rawValue
    @State var sortAscending: Bool = true
    @State var sortOrder: [KeyPathComparator<Document>] = [.init(\.name, order: .forward)]

    var sortField: LibrarySortField {
        LibrarySortField(rawValue: sortFieldRaw) ?? .name
    }

    // Workflow picker state
    @State var showWorkflowPicker = false
    @State var selectedDocumentIdsForBatch: [String] = []

    @EnvironmentObject var libraryManager: LibraryManager
    @EnvironmentObject var windowState: WindowState
    @ObservedObject var featureManager = FeatureManager.shared

    // Column visibility for Table view
    @AppStorage("column_name") var showName = true
    @AppStorage("column_status") var showStatus = true
    @AppStorage("column_progress") var showProgress = true
    @AppStorage("column_output") var showOutput = true
    @AppStorage("column_fileType") var showFileType = true
    @AppStorage("column_path") var showPath = false
    @AppStorage("column_createdDate") var showCreatedDate = true
    @AppStorage("column_modifiedDate") var showModifiedDate = false
    @AppStorage("column_size") var showSize = false

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
    @AppStorage("library.iconViewScale") var iconViewScale: Double = 3.0
    @State var mapCanvasScale: CGFloat = 1.0

    var body: some View {
        withKeyboardShortcuts(
            VStack(spacing: 0) {
                // Inline filter bar (Cmd+F)
                if featureManager.isLibraryFilterToolbarEnabled && showFilterBar {
                    filterBarView
                }

                // Main content
                if filteredDocuments.isEmpty {
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
                        if displayMode == .icon {
                            iconViewScale = min(3.0, iconViewScale + 0.25)
                        } else {
                            mapCanvasScale = min(3.0, mapCanvasScale + 0.25)
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
}

// Components extracted to LibraryViewComponents.swift:
// - MailStyleRow, MapCard, MapGridBackground, ProgressCell, DocumentThumbnailView

// MARK: - Previews

#Preview("Empty") {
    LibraryView(
        documents: [],
        selection: .constant(Set<String>()),
        detailDocument: .constant(nil),
        viewMode: .constant(.icons),
        displayMode: .icon,
        folderId: nil
    )
    .frame(width: 600, height: 500)
}
