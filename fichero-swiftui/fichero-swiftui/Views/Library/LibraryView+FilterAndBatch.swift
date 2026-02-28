import SwiftUI

// MARK: - Filter, Selection, and Batch Extension

extension LibraryView {

    // MARK: - Filtered Documents

    var filteredDocuments: [Document] {
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

    // MARK: - Empty State

    var emptyState: some View {
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

    // MARK: - Tap Handling

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
    func runBatchWorkflow(workflowId: String) async {
        guard !selectedDocumentIdsForBatch.isEmpty else { return }

        // Create batch items - one per document
        let batchItems: [[String: AnyCodableValue]] = selectedDocumentIdsForBatch.map { documentId in
            ["document_id": .string(documentId)]
        }

        guard libraryManager.globalLibrary != nil else {
            print("Error: No global library available")
            return
        }

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
