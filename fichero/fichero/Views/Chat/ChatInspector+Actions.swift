import SwiftUI

extension ChatInspector {
    func addSuggestedDocumentsToScope() {
        guard !suggestedDocumentIDs.isEmpty else { return }

        if let onAddSuggestedDocuments {
            onAddSuggestedDocuments()
            return
        }

        selectedDocuments = mergedSuggestedDocuments
    }

    func removeSelectedFromScope() {
        for id in listSelection {
            selectedDocuments.remove(id)
        }
        listSelection.removeAll()
    }

    func performSearch() async {
        guard !searchText.isEmpty else { return }

        isSearching = true

        do {
            let allDocs: [Document] = try await apiClient.get("/documents", query: ["limit": "100"])
            let filtered = allDocs.filter {
                $0.name.localizedCaseInsensitiveContains(searchText) &&
                    $0.docType == .file
            }
            await MainActor.run {
                searchResults = filtered
                isSearching = false
            }
        } catch {
            chatInspectorLogger.error("Search error: \(error.localizedDescription)")
            await MainActor.run {
                searchResults = []
                isSearching = false
            }
        }
    }

    func handleDrop(providers: [NSItemProvider]) -> Bool {
        for provider in providers {
            guard let typeIdentifier = ChatDocumentDropPayload.firstSupportedTypeIdentifier(in: provider) else {
                continue
            }

            provider.loadItem(forTypeIdentifier: typeIdentifier, options: nil) { item, _ in
                guard let docId = ChatDocumentDropPayload.documentID(from: item) else {
                    return
                }

                Task { @MainActor in
                    selectedDocuments = ChatDocumentScope.attaching([docId], to: selectedDocuments)
                    chatInspectorLogger.info("Added document via drop: \(docId)")
                }
            }
        }
        return true
    }

    func loadScopedDocuments() async {
        guard !selectedDocuments.isEmpty else {
            await MainActor.run { scopedDocuments = [] }
            return
        }

        isLoading = true
        var loadedDocs: [Document] = []

        for docId in selectedDocuments {
            do {
                let doc: Document = try await apiClient.get("/documents/\(docId)")
                loadedDocs.append(doc)
            } catch {
                chatInspectorLogger.error("Failed to load doc \(docId): \(error.localizedDescription)")
            }
        }

        await MainActor.run {
            scopedDocuments = loadedDocs.sorted { $0.name < $1.name }
            isLoading = false
            listSelection = listSelection.intersection(selectedDocuments)
        }
    }

    func extractAllText() async {
        isExtracting = true
        extractionResult = nil

        do {
            let response = try await chatService.extractText(documentIds: nil, force: false)
            await MainActor.run {
                extractionResult = "Done: \(response.extracted) extracted, \(response.skipped) skipped"
                isExtracting = false
            }
        } catch {
            await MainActor.run {
                extractionResult = "Error: \(error.localizedDescription)"
                isExtracting = false
            }
        }
    }
}
