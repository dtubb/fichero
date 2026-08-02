import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "DocumentPickerSheet")

/// Sheet for picking documents to run a workflow on
struct DocumentPickerSheet: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(LibraryManager.self) var libraryManager
    @Environment(DocumentStore.self) var documentStore: DocumentStore

    let workflowId: String
    let workflowName: String

    @State private var searchText = ""
    @State private var selection: Set<String> = []
    @State private var processingOrder: BatchProcessingOrder = .alphabeticalAsc

    @State private var filteredDocuments: [Document] = []
    @State private var selectedDocumentsOrdered: [Document] = []

    private var allDocuments: [Document] {
        documentStore.currentDocuments.filter { $0.docType != .folder }
    }

    /// One recompute into @State when an input changes (search / selection / order /
    /// the store's documents) instead of re-filtering + re-sorting on every body
    /// access through chained computed vars (#3870).
    private func recompute() {
        let all = allDocuments
        if searchText.isEmpty {
            filteredDocuments = all
        } else {
            filteredDocuments = all.filter { document in
                document.name.localizedCaseInsensitiveContains(searchText) ||
                    (document.pageContent?.localizedCaseInsensitiveContains(searchText) ?? false)
            }
        }
        selectedDocumentsOrdered = processingOrder.sort(all.filter { selection.contains($0.id) })
    }

    var body: some View {
        VStack(spacing: 0) {
            // Header
            VStack(spacing: 8) {
                Text("Run Workflow on Documents")
                    .font(.title2)
                    .fontWeight(.semibold)

                Text("Select documents to run \"\(workflowName)\" on")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            .padding()

            Divider()

            // Search bar
            HStack {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(.secondary)
                TextField("Search documents", text: $searchText)
                    .textFieldStyle(.plain)

                if !searchText.isEmpty {
                    Button {
                        searchText = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Clear Search")
                }
            }
            .padding()
            .background(Color(platformColor: .controlBackgroundColor))

            Divider()

            // Document list
            if filteredDocuments.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: searchText.isEmpty ? "doc" : "magnifyingglass")
                        .font(.system(size: 48))
                        .foregroundStyle(.secondary)
                    Text(searchText.isEmpty ? "No documents available" : "No documents found")
                        .font(.headline)
                        .foregroundStyle(.secondary)
                    if searchText.isEmpty {
                        Text("Import files to the library first")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List(filteredDocuments, selection: $selection) { document in
                    DocumentPickerRow(document: document)
                        .tag(document.id)
                }
                .listStyle(.plain)
            }

            Divider()

            // Footer
            HStack {
                Text("\(selection.count) selected")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                Picker("Order", selection: $processingOrder) {
                    ForEach(BatchProcessingOrder.allCases, id: \.self) { order in
                        Text(order.label).tag(order)
                    }
                }
                .pickerStyle(.menu)
                .controlSize(.small)

                Spacer()

                Button("Cancel") {
                    dismiss()
                }
                .keyboardShortcut(.cancelAction)

                Button("Run") {
                    runBatch()
                }
                .buttonStyle(.borderedProminent)
                .disabled(selection.isEmpty)
                .keyboardShortcut(.defaultAction)
            }
            .padding()
        }
        // macOS sheets need an explicit size; on iPhone a fixed 500pt width
        // overflows the ~390pt screen, so let iOS use natural sheet sizing (#3666).
        #if os(macOS)
        .frame(width: 500, height: 600)
        #endif
        .onAppear { recompute() }
        .onChange(of: searchText) { _, _ in recompute() }
        .onChange(of: selection) { _, _ in recompute() }
        .onChange(of: processingOrder) { _, _ in recompute() }
        .onChange(of: documentStore.currentDocuments) { _, _ in recompute() }
    }

    private func runBatch() {
        guard !selection.isEmpty else { return }

        Task { @MainActor in
            await runBatchWorkflow(
                workflowId: workflowId,
                documents: selectedDocumentsOrdered
            )
            dismiss()
        }
    }

    @MainActor
    private func runBatchWorkflow(workflowId: String, documents: [Document]) async {
        guard let library = libraryManager.globalLibrary else {
            logger.error("No global library available; cannot create batch")
            return
        }

        // Create batch items - one per document
        let items: [[String: any Sendable]] = documents.map { document in
            ["document_id": document.id]
        }

        do {
            // Route through the generated client (injects auth + library header)
            let batch = try await library.batchService.createBatch(
                workflowId: workflowId,
                items: items,
                maxConcurrent: 5
            )
            logger.info("Created batch: \(batch.batchId, privacy: .public) with \(documents.count) items")
            // swiftlint:disable:next todo
            // TODO: Navigate to batches sidebar and execute batch with SSE streaming
        } catch {
            logger.error("Error creating batch: \(error.localizedDescription, privacy: .public)")
        }
    }
}

private enum BatchProcessingOrder: CaseIterable {
    case alphabeticalAsc
    case alphabeticalDesc
    case createdOldestFirst
    case createdNewestFirst
    case modifiedOldestFirst
    case modifiedNewestFirst

    var label: String {
        switch self {
        case .alphabeticalAsc: return "Alphabetical (A→Z)"
        case .alphabeticalDesc: return "Alphabetical (Z→A)"
        case .createdOldestFirst: return "Date created (oldest first)"
        case .createdNewestFirst: return "Date created (newest first)"
        case .modifiedOldestFirst: return "Date modified (oldest first)"
        case .modifiedNewestFirst: return "Date modified (newest first)"
        }
    }

    func sort(_ documents: [Document]) -> [Document] {
        switch self {
        case .alphabeticalAsc:
            return documents.sorted {
                $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending
            }
        case .alphabeticalDesc:
            return documents.sorted {
                $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedDescending
            }
        case .createdOldestFirst:
            return documents.sorted { $0.createdAt < $1.createdAt }
        case .createdNewestFirst:
            return documents.sorted { $0.createdAt > $1.createdAt }
        case .modifiedOldestFirst:
            return documents.sorted { $0.updatedAt < $1.updatedAt }
        case .modifiedNewestFirst:
            return documents.sorted { $0.updatedAt > $1.updatedAt }
        }
    }
}

/// Row in the document picker list
private struct DocumentPickerRow: View {
    let document: Document

    var body: some View {
        HStack(spacing: 12) {
            // Icon
            Image(systemName: document.fileType?.icon ?? "doc")
                .font(.title3)
                .foregroundStyle(.secondary)
                .frame(width: 32)

            // Content
            VStack(alignment: .leading, spacing: 4) {
                // #4416: a page's `name` is the engine's upload temp file.
                Text(DocumentTitle.displayName(for: document))
                    .font(.body)
                    .foregroundStyle(.primary)
                    .lineLimit(1)

                if let content = document.pageContent, !content.isEmpty {
                    Text(content)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }

                // Metadata
                HStack(spacing: 12) {
                    if let fileType = document.fileType {
                        Text(fileType.rawValue.uppercased())
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    Text(document.createdAt, style: .date)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }

            Spacer()

            // Status indicator
            StatusBadge(status: document.status)
        }
        .padding(.vertical, 8)
        .contentShape(Rectangle())
    }
}

#Preview {
    DocumentPickerSheet(
        workflowId: "workflow-123",
        workflowName: "Extract Text"
    )
    .environment(LibraryManager.shared)
    .environment(DocumentStore(
        apiClient: LibraryManager.shared.globalLibrary!.apiClient
    ))
}
