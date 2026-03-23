import OSLog
import SwiftUI

// MARK: - Filter, Selection, and Batch Extension

extension LibraryView {
    private var logger: Logger {
        Logger(subsystem: "com.tubb.Fichero", category: "LibraryView")
    }

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

        // Show "Run Workflow..." when at least one document is selected.
        if !selection.isEmpty && featureManager.isWorkflowRunOnSelectionEnabled {
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
    func runBatchWorkflow(workflowId: String) async {
        guard !selectedDocumentIdsForBatch.isEmpty else { return }

        // Create batch items - one per document.
        let batchItems: [[String: any Sendable]] = selectedDocumentIdsForBatch.map { documentId in
            ["document_id": documentId]
        }

        let library = libraryManager.getLibrary(id: windowState.libraryId) ?? libraryManager.globalLibrary
        guard let library else {
            logger.error("Run workflow failed: no active library for window \(self.windowState.libraryId.uuidString)")
            return
        }

        do {
            let batch = try await library.batchService.createBatch(
                workflowId: workflowId,
                items: batchItems,
                maxConcurrent: 5
            )
            try await library.batchService.executeBatch(batchId: batch.batchId)
            logger.info(
                """
                Started batch \(batch.batchId) for workflow \(workflowId) \
                with \(self.selectedDocumentIdsForBatch.count) items
                """
            )
        } catch {
            logger.error("Run workflow failed: \(error.localizedDescription)")
            ErrorService.shared.reportError(error)
        }
    }
}
