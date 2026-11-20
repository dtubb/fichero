import Foundation

enum ChatScopeBuilder {
    static func currentScopeDocumentIds(
        browserSelection: Set<String>,
        currentDocuments: [Document],
        detailDocument: Document?
    ) -> [String] {
        let selectedIds = currentDocuments
            .filter { browserSelection.contains($0.id) && $0.docType != .folder }
            .map(\.id)
        if !selectedIds.isEmpty {
            return selectedIds
        }

        if let detailDocument, detailDocument.docType != .folder {
            return [detailDocument.id]
        }

        return currentDocuments
            .filter { $0.docType != .folder }
            .map(\.id)
    }
}
