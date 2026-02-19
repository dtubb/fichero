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

/// Grid/List/Table/Map view of documents
struct LibraryView: View {
    let documents: [Document]
    @Binding var selection: Set<String>
    @Binding var detailDocument: Document?
    @Binding var viewMode: LibraryLayout
    let displayMode: ViewDisplayMode  // Universal view mode from toolbar

    @State private var searchText: String = ""
    @State var sortOrder: [KeyPathComparator<Document>] = [
        .init(\.name, order: .forward)
    ]

    // Workflow picker state
    @State private var showWorkflowPicker = false
    @State private var selectedDocumentIdsForBatch: [String] = []

    @EnvironmentObject var libraryManager: LibraryManager

    // Column visibility for Table view
    @AppStorage("column_name") private var showName = true
    @AppStorage("column_status") private var showStatus = true
    @AppStorage("column_progress") private var showProgress = true
    @AppStorage("column_output") private var showOutput = true
    @AppStorage("column_fileType") private var showFileType = true
    @AppStorage("column_path") private var showPath = false
    @AppStorage("column_createdDate") private var showCreatedDate = true
    @AppStorage("column_modifiedDate") private var showModifiedDate = false
    @AppStorage("column_size") private var showSize = false

    // Map view positions
    @State var mapPositions: [String: CGPoint] = [:]

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
        VStack(spacing: 0) {
            // View-specific toolbar at top
            LibraryViewToolbar(
                viewMode: $viewMode,
                showColumnConfig: true,
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
        .searchable(text: $searchText, prompt: "Search documents")
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
    }
}

// MARK: - View Components & Helpers

extension LibraryView {
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
                Text(doc.name)
                    .lineLimit(1)
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
        if NSEvent.modifierFlags.contains(.command) {
            if selection.contains(doc.id) {
                selection.remove(doc.id)
            } else {
                selection.insert(doc.id)
            }
        } else {
            selection = [doc.id]
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

#Preview("Empty") {
    LibraryView(
        documents: [],
        selection: .constant(Set<String>()),
        detailDocument: .constant(nil),
        viewMode: .constant(.icons),
        displayMode: .icon
    )
    .frame(width: 600, height: 500)
}
