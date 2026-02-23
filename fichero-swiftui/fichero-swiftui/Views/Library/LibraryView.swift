import SwiftUI
import UniformTypeIdentifiers

/// Column definition for table view
struct ColumnDefinition: Identifiable, Hashable {
    let id: String
    let title: String
    let defaultVisible: Bool
    let minWidth: CGFloat
    let idealWidth: CGFloat

    static let allColumns: [ColumnDefinition] = [
        ColumnDefinition(id: "name", title: "Name", defaultVisible: true, minWidth: 150, idealWidth: 200),
        ColumnDefinition(id: "status", title: "Status", defaultVisible: true, minWidth: 80, idealWidth: 100),
        ColumnDefinition(id: "progress", title: "Progress", defaultVisible: true, minWidth: 80, idealWidth: 100),
        ColumnDefinition(id: "output", title: "Output", defaultVisible: true, minWidth: 150, idealWidth: 250),
        ColumnDefinition(id: "fileType", title: "Type", defaultVisible: true, minWidth: 60, idealWidth: 80),
        ColumnDefinition(id: "path", title: "Path", defaultVisible: false, minWidth: 100, idealWidth: 150),
        ColumnDefinition(id: "createdDate", title: "Created", defaultVisible: true, minWidth: 80, idealWidth: 100),
        ColumnDefinition(id: "modifiedDate", title: "Modified", defaultVisible: false, minWidth: 80, idealWidth: 100),
        ColumnDefinition(id: "size", title: "Size", defaultVisible: false, minWidth: 60, idealWidth: 80)
    ]
}

/// Sortable fields for library documents
enum LibrarySortField: String, CaseIterable, Identifiable {
    case name = "Name"
    case createdAt = "Date Created"
    case updatedAt = "Date Modified"
    case fileType = "Type"
    case status = "Status"

    var id: String { rawValue }

    var icon: String {
        switch self {
        case .name: return "textformat"
        case .createdAt: return "calendar.badge.plus"
        case .updatedAt: return "calendar.badge.clock"
        case .fileType: return "doc"
        case .status: return "circle.dotted"
        }
    }

    func comparator(ascending: Bool) -> [KeyPathComparator<Document>] {
        let order: SortOrder = ascending ? .forward : .reverse
        switch self {
        case .name: return [.init(\.name, order: order)]
        case .createdAt: return [.init(\.createdAt, order: order)]
        case .updatedAt: return [.init(\.updatedAt, order: order)]
        case .fileType: return [.init(\.sortableFileType, order: order)]
        case .status: return [.init(\.status.rawValue, order: order)]
        }
    }
}

/// Grid/List/Table/Map view of documents
struct LibraryView: View {
    let documents: [Document]
    @Binding var selection: Set<String>
    @Binding var detailDocument: Document?
    @Binding var viewMode: LibraryLayout
    let displayMode: ViewDisplayMode  // Universal view mode from toolbar

    let folderId: String?  // Current folder ID for per-folder sort persistence
    var onRequestFocus: () -> Void = {}  // Called on tap to pull keyboard focus into content area

    @State private var searchText: String = ""
    @State private var showFilterBar = false
    @FocusState private var filterFieldFocused: Bool
    @State var sortFieldRaw: String = LibrarySortField.name.rawValue
    @State var sortAscending: Bool = true
    @State var sortOrder: [KeyPathComparator<Document>] = [.init(\.name, order: .forward)]

    var sortField: LibrarySortField {
        LibrarySortField(rawValue: sortFieldRaw) ?? .name
    }

    // Workflow picker state
    @State private var showWorkflowPicker = false
    @State private var selectedDocumentIdsForBatch: [String] = []

    @EnvironmentObject var libraryManager: LibraryManager

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

    // Selection anchor for Shift+click range select
    @State var selectionAnchor: String?

    // Grid column count for arrow key navigation (updated by GeometryReader in iconsView)
    @State var gridColumnCount: Int = 4

    // Zoom scale for icon and map views (persisted per-app)
    @AppStorage("library.iconViewScale") var iconViewScale: Double = 1.0
    @State var mapCanvasScale: CGFloat = 1.0

    var visibleColumns: [ColumnDefinition] {
        ColumnDefinition.allColumns.filter { col in
            switch col.id {
            case "name": return showName
            case "status": return showStatus
            case "progress": return showProgress
            case "output": return showOutput
            case "fileType": return showFileType
            case "path": return showPath
            case "createdDate": return showCreatedDate
            case "modifiedDate": return showModifiedDate
            case "size": return showSize
            default: return false
            }
        }
    }

    var filteredDocuments: [Document] {
        // Show both files AND folders in the gallery view
        var docs = documents

        if !searchText.isEmpty {
            docs = docs.filter {
                $0.name.localizedCaseInsensitiveContains(searchText) ||
                ($0.pageContent?.localizedCaseInsensitiveContains(searchText) ?? false) ||
                $0.status.rawValue.localizedCaseInsensitiveContains(searchText)
            }
        }

        return docs.sorted(using: sortOrder)
    }

    var body: some View {
        withKeyboardShortcuts(
            VStack(spacing: 0) {
                // Inline filter bar (Cmd+F)
                if showFilterBar {
                    filterBarView
                }

                // View-specific toolbar at top
                LibraryViewToolbar(
                    viewMode: $viewMode,
                    showColumnConfig: true,
                    displayMode: displayMode,
                    sortFieldRaw: $sortFieldRaw,
                    sortAscending: $sortAscending,
                    iconViewScale: $iconViewScale,
                    mapCanvasScale: $mapCanvasScale,
                    showName: $showName,
                    showStatus: $showStatus,
                    showProgress: $showProgress,
                    showOutput: $showOutput,
                    showFileType: $showFileType,
                    showPath: $showPath,
                    showCreatedDate: $showCreatedDate,
                    showModifiedDate: $showModifiedDate,
                    showSize: $showSize,
                    onResetColumns: resetColumns
                )

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
                Button("") {
                    showFilterBar = true
                    filterFieldFocused = true
                }
                .keyboardShortcut("f", modifiers: .command)
                .hidden()
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
            .focusedSceneValue(\.runWorkflowOnSelection, selection.count >= 2 ? {
                selectedDocumentIdsForBatch = Array(selection)
                showWorkflowPicker = true
            } : nil)
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
                // Sync sort menu when column headers are clicked
                guard let first = newOrder.first else { return }
                let ascending = first.order == .forward
                if first.keyPath == \Document.name {
                    sortFieldRaw = LibrarySortField.name.rawValue
                    sortAscending = ascending
                } else if first.keyPath == \Document.createdAt {
                    sortFieldRaw = LibrarySortField.createdAt.rawValue
                    sortAscending = ascending
                } else if first.keyPath == \Document.updatedAt {
                    sortFieldRaw = LibrarySortField.updatedAt.rawValue
                    sortAscending = ascending
                } else if first.keyPath == \Document.sortableFileType {
                    sortFieldRaw = LibrarySortField.fileType.rawValue
                    sortAscending = ascending
                } else if first.keyPath == \Document.status.rawValue {
                    sortFieldRaw = LibrarySortField.status.rawValue
                    sortAscending = ascending
                }
                saveSortSettings(for: folderId)
            }
        )
    }
}

// MARK: - View Components & Helpers

extension LibraryView {
    // MARK: - Filter Bar

    var filterBarView: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(.secondary)
                    .font(.system(size: 12))

                TextField("Filter", text: $searchText)
                    .textFieldStyle(.plain)
                    .font(.system(size: 13))
                    .focused($filterFieldFocused)

                if !searchText.isEmpty {
                    Button {
                        searchText = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                }

                Button("Done") {
                    searchText = ""
                    showFilterBar = false
                }
                .buttonStyle(.borderless)
                .font(.system(size: 12))
                .keyboardShortcut(.escape, modifiers: [])
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(.bar)

            Divider()
        }
    }

    // MARK: - Sort Order Sync

    /// Sync the @State sortOrder from persisted values
    func syncSortOrder() {
        let field = LibrarySortField(rawValue: sortFieldRaw) ?? .name
        sortOrder = field.comparator(ascending: sortAscending)
    }

    // MARK: - Per-Folder Sort Persistence

    private func sortFieldKey(for id: String?) -> String {
        id.map { "librarySortField_\($0)" } ?? "librarySortField"
    }

    private func sortAscendingKey(for id: String?) -> String {
        id.map { "librarySortAscending_\($0)" } ?? "librarySortAscending"
    }

    func loadSortSettings(for id: String?) {
        let defaults = UserDefaults.standard
        sortFieldRaw = defaults.string(forKey: sortFieldKey(for: id)) ?? LibrarySortField.name.rawValue
        if let saved = defaults.object(forKey: sortAscendingKey(for: id)) as? Bool {
            sortAscending = saved
        } else {
            sortAscending = true
        }
    }

    func saveSortSettings(for id: String?) {
        let defaults = UserDefaults.standard
        defaults.set(sortFieldRaw, forKey: sortFieldKey(for: id))
        defaults.set(sortAscending, forKey: sortAscendingKey(for: id))
    }

    // MARK: - Column Management

    func resetColumns() {
        showName = true
        showStatus = true
        showProgress = true
        showOutput = true
        showFileType = true
        showPath = false
        showCreatedDate = true
        showModifiedDate = false
        showSize = false
    }

    // Display mode views extracted to LibraryView+DisplayModes.swift

    // MARK: - Table Cell View

    @ViewBuilder
    // swiftlint:disable:next function_body_length cyclomatic_complexity
    func tableCellView(for columnId: String, document doc: Document) -> some View {
        switch columnId {
        case "name":
            HStack(spacing: 8) {
                // Show folder icon for folders, file type icon for files
                if doc.docType == .folder {
                    Image(systemName: "folder.fill")
                        .foregroundColor(.accentColor)
                        .frame(width: 16)
                } else {
                    Image(systemName: doc.fileType?.icon ?? "doc")
                        .foregroundColor(.secondary)
                        .frame(width: 16)
                }
                EditableDocumentName(
                    document: doc,
                    isRenaming: renamingDocumentId == doc.id,
                    editingName: $editingName,
                    onCommit: commitRename,
                    onCancel: cancelRename
                )
            }
        case "status":
            StatusBadge(status: doc.status)
        case "progress":
            ProgressCell(document: doc)
        case "output":
            Text(doc.pageContent ?? "-")
                .font(.caption)
                .foregroundColor(.secondary)
                .lineLimit(1)
                .help(doc.pageContent ?? "")
        case "fileType":
            if doc.docType == .folder {
                Text("Folder")
                    .font(.caption)
                    .foregroundColor(.secondary)
            } else {
                Text(doc.fileType?.rawValue.capitalized ?? "-")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        case "path":
            Text(doc.path ?? "-")
                .font(.caption)
                .foregroundColor(.secondary)
                .lineLimit(1)
                .help(doc.path ?? "")
        case "createdDate":
            Text(doc.createdAt, style: .date)
                .font(.caption)
                .foregroundColor(.secondary)
        case "modifiedDate":
            Text(doc.updatedAt, style: .date)
                .font(.caption)
                .foregroundColor(.secondary)
        case "size":
            Text("-")
                .font(.caption)
                .foregroundColor(.secondary)
        default:
            Text("-")
                .foregroundColor(.secondary)
        }
    }

    // MARK: - Empty State

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "doc.text.magnifyingglass")
                .font(.system(size: 48))
                .foregroundColor(.secondary)

            Text("No Documents")
                .font(.headline)

            if !searchText.isEmpty {
                Text("No results for \"\(searchText)\"")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            } else {
                Text("Select a collection to view documents")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Helpers

    func handleTap(_ doc: Document) {
        onRequestFocus()
        let modifiers = NSEvent.modifierFlags
        if modifiers.contains(.shift), let anchor = selectionAnchor {
            // Shift+click: range select from anchor to clicked item
            let docs = filteredDocuments
            if let anchorIndex = docs.firstIndex(where: { $0.id == anchor }),
               let clickIndex = docs.firstIndex(where: { $0.id == doc.id }) {
                let range = min(anchorIndex, clickIndex)...max(anchorIndex, clickIndex)
                let rangeIds = Set(docs[range].map(\.id))
                if modifiers.contains(.command) {
                    // Shift+Cmd+click: add range to existing selection
                    selection.formUnion(rangeIds)
                } else {
                    // Shift+click: replace selection with range
                    selection = rangeIds
                }
            }
            // Don't update anchor on Shift+click
        } else if modifiers.contains(.command) {
            // Cmd+click: toggle individual item
            if selection.contains(doc.id) {
                selection.remove(doc.id)
            } else {
                selection.insert(doc.id)
            }
            selectionAnchor = doc.id
        } else {
            // Plain click: replace selection
            selection = [doc.id]
            selectionAnchor = doc.id
        }
    }

    private func resetColumnVisibility() {
        showName = true
        showStatus = true
        showProgress = true
        showOutput = true
        showFileType = true
        showPath = false
        showCreatedDate = true
        showModifiedDate = false
        showSize = false
    }

    // MARK: - Context Menu

    @ViewBuilder
    func documentContextMenu(for document: Document) -> some View {
        Button {
            startRename(for: document)
        } label: {
            Label("Rename", systemImage: "pencil")
        }

        // Only show "Run Workflow..." if 2+ documents are selected
        if selection.count >= 2 {
            Button {
                selectedDocumentIdsForBatch = Array(selection)
                showWorkflowPicker = true
            } label: {
                Label("Run Workflow...", systemImage: "flowchart")
            }
        }
    }

    // MARK: - Batch Execution

    @MainActor
    // swiftlint:disable:next function_body_length cyclomatic_complexity
    private func runBatchWorkflow(workflowId: String) async {
        guard !selectedDocumentIdsForBatch.isEmpty else { return }

        // Create batch items - one per document
        let batchItems: [[String: AnyCodableValue]] = selectedDocumentIdsForBatch.map { documentId in
            ["document_id": .string(documentId)]
        }

        // Get API client from environment
        guard libraryManager.globalLibrary != nil else {
            print("Error: No global library available")
            return
        }

        // Create batch request payload
        let requestBody: [String: Any] = [
            "workflow_id": workflowId,
            "items": batchItems.map { item in
                item.mapValues { value in
                    switch value {
                    case .string(let str): return str
                    case .int(let int): return String(int)
                    case .double(let double): return String(double)
                    case .bool(let bool): return String(bool)
                    case .array(let arr): return String(describing: arr)
                    case .dictionary(let dict): return String(describing: dict)
                    case .null: return "null"
                    }
                }
            },
            "max_concurrent": 5
        ]

        do {
            let jsonData = try JSONSerialization.data(withJSONObject: requestBody)

            // Make direct HTTP request to batch API
            guard let url = URL(string: "http://localhost:8765/api/batches") else {
                print("Error: Invalid URL")
                return
            }

            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = jsonData

            let (data, response) = try await URLSession.shared.data(for: request)

            guard let httpResponse = response as? HTTPURLResponse else {
                print("Error: Invalid response")
                return
            }

            if httpResponse.statusCode == 200 {
                if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let batchId = json["batch_id"] as? String {
                    print("Created batch: \(batchId) with \(selectedDocumentIdsForBatch.count) items")
                    // swiftlint:disable:next todo
                    // TODO: Navigate to batches sidebar and execute batch with SSE streaming
                    // This would be done via a BatchService similar to ChainService
                } else {
                    print("Created batch with \(selectedDocumentIdsForBatch.count) items")
                }
            } else {
                print("Error: HTTP \(httpResponse.statusCode)")
                if let errorText = String(data: data, encoding: .utf8) {
                    print("Error details: \(errorText)")
                }
            }
        } catch {
            print("Error creating batch: \(error.localizedDescription)")
        }
    }
}

// Components extracted to LibraryViewComponents.swift:
// - MailStyleRow, MapCard, MapGridBackground, ProgressCell, DocumentThumbnailView

// MARK: - Previews

// swiftlint:disable file_length
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
