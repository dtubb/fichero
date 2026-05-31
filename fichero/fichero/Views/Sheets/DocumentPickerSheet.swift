import SwiftUI

/// Sheet for picking documents to run a workflow on
struct DocumentPickerSheet: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject var libraryManager: LibraryManager
    @EnvironmentObject var documentStore: DocumentStore

    let workflowId: String
    let workflowName: String

    @State private var searchText = ""
    @State private var selection: Set<String> = []
    @State private var processingOrder: BatchProcessingOrder = .alphabeticalAsc

    private var allDocuments: [Document] {
        documentStore.currentDocuments.filter { $0.docType != .folder }
    }

    private var filteredDocuments: [Document] {
        if searchText.isEmpty {
            return allDocuments
        }
        return allDocuments.filter { document in
            document.name.localizedCaseInsensitiveContains(searchText) ||
                (document.pageContent?.localizedCaseInsensitiveContains(searchText) ?? false)
        }
    }

    private var selectedDocumentsOrdered: [Document] {
        let selected = allDocuments.filter { selection.contains($0.id) }
        return processingOrder.sort(selected)
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
                }
            }
            .padding()
            .background(Color(nsColor: .controlBackgroundColor))

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
        .frame(width: 500, height: 600)
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
    // swiftlint:disable:next function_body_length cyclomatic_complexity
    private func runBatchWorkflow(workflowId: String, documents: [Document]) async {
        guard libraryManager.globalLibrary != nil else {
            print("Error: No global library available")
            return
        }

        // Create batch items - one per document
        let batchItems: [[String: AnyCodableValue]] = documents.map { document in
            ["document_id": .string(document.id)]
        }

        // Create batch request payload
        let requestBody: [String: Any] = [
            "workflow_id": workflowId,
            "items": batchItems.map { item -> [String: Any] in
                item.mapValues { value -> Any in
                    switch value {
                    case .string(let str): return str
                    case .int(let int): return int
                    case .double(let double): return double
                    case .bool(let bool): return bool
                    case .array(let arr): return arr
                    case .dictionary(let dict): return dict
                    case .null: return NSNull()
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
            request.addEngineAuth()
            request.httpBody = jsonData

            let (data, response) = try await URLSession.shared.data(for: request)

            guard let httpResponse = response as? HTTPURLResponse else {
                print("Error: Invalid response")
                return
            }

            if httpResponse.statusCode == 200 {
                if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let batchId = json["batch_id"] as? String {
                    print("Created batch: \(batchId) with \(documents.count) items")
                    // swiftlint:disable:next todo
                    // TODO: Navigate to batches sidebar and execute batch with SSE streaming
                } else {
                    print("Created batch with \(documents.count) items")
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
                Text(document.name)
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
    .environmentObject(LibraryManager.shared)
    .environmentObject(DocumentStore(
        apiClient: LibraryManager.shared.globalLibrary!.apiClient
    ))
}
