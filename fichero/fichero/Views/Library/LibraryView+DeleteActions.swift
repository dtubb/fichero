import SwiftUI

private struct DocumentDeleteActionParams: Encodable {
    let docId: String

    enum CodingKeys: String, CodingKey {
        case docId = "doc_id"
    }
}

// MARK: - Delete Actions

extension LibraryView {
    /// Prompt user to confirm deletion of selected documents.
    ///
    /// Selection may span expanded child outline rows (#4198). Delete acts
    /// on the DOCUMENT rows only: a page/artifact row may one day be
    /// deletable, but an entity/claim row is a knowledge-graph operation
    /// with its own consequences and undo story — until each kind has a
    /// defined answer, we act on the documents and SAY what is skipped.
    /// The old silent no-op for a child-only selection looked like the
    /// delete worked; that is the worst option.
    func promptDeleteSelected() {
        let selectedDocs = filteredDocuments.filter { selection.contains($0.id) }
        deleteSkippedNote = Self.skippedChildRowNote(
            for: selection.subtracting(selectedDocs.map(\.id))
        )
        guard !selectedDocs.isEmpty else {
            // Child-only selection: the SAME dialog presents as a
            // "Nothing Deleted" notice (empty documentsToDelete) — one
            // presentation modifier, see applyDeleteConfirmation.
            if deleteSkippedNote != nil {
                documentsToDelete = []
                showDeleteConfirmation = true
            }
            return
        }
        documentsToDelete = selectedDocs
        showDeleteConfirmation = true
    }

    /// Human summary of the selected rows delete will NOT touch, or nil when
    /// everything selected is a document. Pure and static for testability.
    ///
    /// `nonisolated` is LOAD-BEARING: `LibraryView: View` is MainActor-
    /// isolated under the macOS 26 SDK, so without it this static inherits
    /// MainActor and any off-main caller (Swift Testing runs suites on pool
    /// threads) hits `dispatch_assert_queue_fail` — a SIGTRAP that killed
    /// the whole test process, non-deterministically by thread scheduling
    /// (five crash reports, 2026-07-28 gates 5-8). A pure String function
    /// has no business on an actor.
    nonisolated static func skippedChildRowNote(for ids: Set<String>) -> String? {
        guard !ids.isEmpty else { return nil }
        var counts: [LibraryOutlineNode.ChildType: Int] = [:]
        var other = 0
        for id in ids {
            if let type = LibraryOutlineNode.childRowType(forNodeId: id) {
                counts[type, default: 0] += 1
            } else {
                other += 1
            }
        }
        var parts = LibraryOutlineNode.ChildType.allCases.compactMap { type -> String? in
            counts[type].map { type.groupLabel(count: $0) }
        }
        if other > 0 {
            parts.append("\(other) item\(other == 1 ? "" : "s")")
        }
        guard !parts.isEmpty else { return nil }
        return "Skipped \(parts.joined(separator: ", ")) — deleting these "
            + "from the outline isn't supported yet. Select the document row "
            + "to delete the whole document."
    }

    /// Perform the actual deletion after confirmation
    func performDeleteSelected() async {
        guard let library = libraryManager.getLibrary(id: windowState.libraryId) else { return }
        for doc in documentsToDelete {
            do {
                _ = try await library.actionsService.invokeAction(
                    name: "document.delete",
                    params: DocumentDeleteActionParams(docId: doc.id)
                )
            } catch {
                ErrorService.shared.reportError(
                    ErrorModel.fileSystemError(
                        message: "Failed to delete \"\(doc.name)\".",
                        context: [
                            "operation": "delete_document",
                            "document_id": doc.id,
                            "underlying_error": error.localizedDescription
                        ]
                    )
                )
            }
        }
        // Clear selection for deleted items — including any of their child
        // outline rows still selected (#4198), which would otherwise dangle.
        for doc in documentsToDelete {
            selection.remove(doc.id)
            selection = selection.filter { !$0.hasPrefix("\(doc.id):") }
        }
        documentsToDelete = []
        deleteSkippedNote = nil
        await library.documentStore.refresh()
    }

    /// Return-to-open (#4160): acts on the KEYBOARD CURSOR row (visual order,
    /// never Set hash order) and matches double-click exactly — navigate into
    /// containers, otherwise show in the detail pane.
    func openSelectedDocument() {
        guard let primaryId = orderedPrimarySelectionId else { return }
        if isShowingEntitiesCollection,
           let entity = filteredEntities.first(where: { entitySelectionId(for: $0) == primaryId }) {
            focusEntityIfPossible(entity)
            return
        }
        guard let doc = navigableDocument(for: primaryId) else { return }
        openDocument(doc)
    }

    /// Select all visible rows. In table mode that is the VISIBLE outline
    /// rows — expanded pages/artifacts/entities/claims included, exactly
    /// like ⌘A in Finder's list view (#4198). Other modes keep the flat
    /// document set.
    func selectAll() {
        if isShowingEntitiesCollection {
            selection = Set(filteredEntities.map { entitySelectionId(for: $0) })
        } else if displayMode == .table {
            selection = Set(LibraryOutlineNode.visibleIds(of: outlineNodes, expanded: outlineExpanded))
        } else {
            selection = Set(filteredDocuments.map(\.id))
        }
    }
}
