import FicheroAPIClient
import SwiftUI

// MARK: - Selection, Tap Handling, and Open Affordances

extension LibraryView {

    // MARK: - Canvas / Spatial selection bridge (#4192)

    /// The canvas and spatial view modes speak `SpatialNode` ids (`doc:<id>`)
    /// and hold ONE selected node; every other view mode speaks raw document
    /// ids and holds a `Set`. They used to be two separate pieces of state —
    /// the canvas kept a private `spatialSelectedNodeId` that nothing read back
    /// — so selecting a row in List and switching to Canvas showed nothing
    /// selected, and clicking a card in Canvas never reached the inspector,
    /// the toolbar, or any of the selection-driven commands.
    ///
    /// This is the one binding both halves share: the canvas reads and writes
    /// the SAME `selection` the list, table, icon and column modes use.
    var canvasSelectedNodeId: Binding<String?> {
        Binding(
            get: { Self.canvasNodeId(forSelection: selection) },
            set: { selection = Self.librarySelection(forCanvasNodeId: $0) }
        )
    }

    /// The node the canvas should show as selected for a library selection.
    ///
    /// A multi-selection maps to nil: the canvas's model is a single node, and
    /// silently showing one arbitrary member of a five-row selection would be a
    /// lie about what is selected. Nothing is lost — switching back to a list
    /// mode still has the full set.
    ///
    /// `nonisolated` is LOAD-BEARING: a static on a `View` inherits the type's
    /// MainActor isolation under the macOS 26 SDK, and the Swift Testing suite
    /// that calls this runs on a cooperative thread — the off-main call SIGTRAPs
    /// the whole test process (#4201).
    nonisolated static func canvasNodeId(forSelection selection: Set<String>) -> String? {
        guard selection.count == 1, let documentId = selection.first else { return nil }
        return SpatialLibraryProjector.nodeId(forDocument: documentId)
    }

    /// The library selection for a node the user clicked on the canvas. A
    /// non-document node (an entity orb, a standalone canvas item) selects no
    /// document — it has no row in any list mode to select.
    nonisolated static func librarySelection(forCanvasNodeId nodeId: String?) -> Set<String> {
        guard let nodeId, let documentId = SpatialLibraryProjector.documentId(fromNodeId: nodeId) else {
            return []
        }
        return [documentId]
    }

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
        // Shift+click: range select from anchor to clicked item — over the
        // ACTIVE column's order in columns mode (#4160 step 4).
        let docs = keyboardNavigationDocuments
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

    /// Whether a PLAIN tap opens a navigable container in place (#2666).
    /// Regular width drills in only when the sidebar is hidden — the sidebar is
    /// the primary folder navigator there, so a single click is selection.
    /// Compact width (iPhone) has NO persistent sidebar even though the shell's
    /// `showSidebar` state stays true, so the row tap is the only way into a
    /// folder — without the compact clause, folders on iPhone highlighted but
    /// never opened, cutting off every document nested below the root.
    /// nonisolated: pure, testable off-main (#4201).
    nonisolated static func plainTapNavigatesInto(
        isNavigableContainer: Bool,
        sidebarHidden: Bool,
        isCompactWidth: Bool
    ) -> Bool {
        isNavigableContainer && (sidebarHidden || isCompactWidth)
    }

    private func handlePlainClick(_ doc: Document) {
        // Plain click: replace selection.
        selection = [doc.id]
        selectionAnchor = doc.id
        detailDocument = doc
        if Self.plainTapNavigatesInto(
            isNavigableContainer: canNavigateInto(doc),
            sidebarHidden: sidebarHidden,
            isCompactWidth: horizontalSizeClass == .compact
        ) {
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
        guard let pendingId = libraryManager.pendingOpenDocumentId else { return }
        if let doc = documents.first(where: { $0.id == pendingId }) {
            libraryManager.pendingOpenDocumentId = nil
            openDocument(doc)
            return
        }
        // Test hook (InspectorFlowsUITests): the wanted document may be nested
        // under a collection and absent from the *current* folder listing. Under
        // XCUITest only, fetch it by id and show it directly so the inspector
        // flow tests can open a seeded child document without navigating folders.
        // Production behaviour is unchanged — the fetch branch never runs outside
        // a UI test.
        guard isUITesting() else { return }
        // Claim the id (nil it) so overlapping revision ticks don't each launch a
        // fetch; on failure — e.g. the engine isn't connected yet — restore it so
        // a later revision retries once the connection is live.
        libraryManager.pendingOpenDocumentId = nil
        Task { @MainActor in
            if let doc = try? await documentStore.documentService.getDocument(pendingId) {
                detailDocument = doc
            } else {
                libraryManager.pendingOpenDocumentId = pendingId
            }
        }
    }
}
