import FicheroAPIClient
import SwiftUI

// MARK: - Selection, Tap Handling, and Open Affordances

extension LibraryView {

    // MARK: - Tap Handling

    func canNavigateInto(_ doc: Document) -> Bool {
        doc.isNavigableContainer
    }

    /// Finder-style double-click: keep the source row selected in THIS window,
    /// then open it in place — navigate into containers, otherwise preview the
    /// document. Explicit New Tab / New Window affordances stay in the context
    /// menu. (#3364)
    func handleDoubleClick(_ doc: Document) {
        listScrollCenterTarget = doc.id
        openDocument(doc)
    }

    func handleTap(_ doc: Document) {
        onRequestFocus()
        #if os(macOS)
        let modifiers = NSEvent.modifierFlags
        if modifiers.contains(.shift), let anchor = selectionAnchor {
            handleShiftClick(doc, anchor: anchor, commandKeyDown: modifiers.contains(.command))
        } else if modifiers.contains(.command) {
            handleCommandClick(doc)
        } else {
            handlePlainClick(doc)
        }
        #else
        handlePlainClick(doc)
        #endif
    }

    private func handleShiftClick(_ doc: Document, anchor: String, commandKeyDown: Bool) {
        // Shift+click: range select from anchor to clicked item.
        let docs = filteredDocuments
        guard let anchorIndex = docs.firstIndex(where: { $0.id == anchor }),
              let clickIndex = docs.firstIndex(where: { $0.id == doc.id }) else {
            return
        }
        let range = min(anchorIndex, clickIndex)...max(anchorIndex, clickIndex)
        let rangeIds = Set(docs[range].map(\.id))
        if commandKeyDown {
            selection.formUnion(rangeIds)
        } else {
            selection = rangeIds
        }
    }

    private func handleCommandClick(_ doc: Document) {
        // Cmd+click: toggle individual item.
        if selection.contains(doc.id) {
            selection.remove(doc.id)
        } else {
            selection.insert(doc.id)
        }
        selectionAnchor = doc.id
    }

    private func handlePlainClick(_ doc: Document) {
        // Plain click: replace selection.
        selection = [doc.id]
        selectionAnchor = doc.id
        detailDocument = doc
        if sidebarHidden, canNavigateInto(doc) {
            onNavigateInto(doc)
        }
    }

    func handleEntityTap(_ entity: Components.Schemas.KnowledgeEntity) {
        onRequestFocus()
        #if os(macOS)
        let modifiers = NSEvent.modifierFlags
        if modifiers.contains(.shift), let anchor = selectionAnchor {
            handleEntityShiftClick(entity, anchor: anchor, commandKeyDown: modifiers.contains(.command))
        } else if modifiers.contains(.command) {
            handleEntityCommandClick(entity)
        } else {
            handleEntityPlainClick(entity)
        }
        #else
        handleEntityPlainClick(entity)
        #endif
        focusEntityIfPossible(entity)
    }

    func handleEntityDoubleClick(_ entity: Components.Schemas.KnowledgeEntity) {
        let entityId = entitySelectionId(for: entity)
        withAnimation(.easeInOut(duration: 0.2)) {
            selection = [entityId]
            selectionAnchor = entityId
        }
        listScrollCenterTarget = entityId
        focusEntityIfPossible(entity)
    }

    private func handleEntityShiftClick(
        _ entity: Components.Schemas.KnowledgeEntity,
        anchor: String,
        commandKeyDown: Bool
    ) {
        let items = filteredEntities
        guard let anchorIndex = items.firstIndex(where: { entitySelectionId(for: $0) == anchor }),
              let clickIndex = items.firstIndex(where: { entitySelectionId(for: $0) == entitySelectionId(for: entity) }) else {
            return
        }
        let range = min(anchorIndex, clickIndex)...max(anchorIndex, clickIndex)
        let rangeIds = Set(range.map { entitySelectionId(for: items[$0]) })
        if commandKeyDown {
            selection.formUnion(rangeIds)
        } else {
            selection = rangeIds
        }
    }

    private func handleEntityCommandClick(_ entity: Components.Schemas.KnowledgeEntity) {
        let entityId = entitySelectionId(for: entity)
        if selection.contains(entityId) {
            selection.remove(entityId)
        } else {
            selection.insert(entityId)
        }
        selectionAnchor = entityId
    }

    private func handleEntityPlainClick(_ entity: Components.Schemas.KnowledgeEntity) {
        let entityId = entitySelectionId(for: entity)
        selection = [entityId]
        selectionAnchor = entityId
    }

    // MARK: - Open Affordances (#1685)

    /// In-window "Open": navigate into containers, otherwise show the doc in
    /// the detail/preview pane. Mirrors the existing double-click open path.
    func openDocument(_ doc: Document) {
        selection = [doc.id]
        selectionAnchor = doc.id
        if canNavigateInto(doc) {
            onNavigateInto(doc)
        } else {
            detailDocument = doc
        }
    }

    /// "Open in New Tab / New Window": open a fresh window on this library via
    /// the shared Safari new-window path, asking it to focus this document
    /// once its rows load.
    func openDocumentInNewWindow(_ doc: Document, asTab: Bool) {
        WindowOpener.open(
            libraryId: windowState.libraryId,
            documentId: doc.id,
            asTab: asTab,
            using: openWindow
        )
    }

    /// Hand-off consumer for a cross-window open intent. When a window is
    /// opened via "Open in New Tab/Window" with a pending document id, select
    /// and preview that document here, then clear the intent so sibling
    /// windows don't also consume it.
    func consumePendingOpen() {
        guard let pendingId = libraryManager.pendingOpenDocumentId,
              let doc = documents.first(where: { $0.id == pendingId }) else { return }
        libraryManager.pendingOpenDocumentId = nil
        openDocument(doc)
    }
}
