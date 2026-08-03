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
    var canvasSelectedNodeIds: Binding<Set<String>> {
        Binding(
            get: { Self.canvasNodeIds(forSelection: selection) },
            set: { selection = Self.librarySelection(forCanvasNodeIds: $0) }
        )
    }

    /// The nodes the canvas should show as selected for a library selection.
    ///
    /// This used to return `String?` and map any multi-selection to nil, on the
    /// stated grounds that "the canvas's model is a single node" (#4409). That
    /// premise was false: `LibraryView.selection` is a `Set<String>` and
    /// `CanvasInteractionController.selectionSet` is a `Set<String>` — this
    /// bridge was the ONLY single-valued link in the chain, and it discarded
    /// the rest. Both ends were right and the adapter threw the answer away.
    ///
    /// `nonisolated` is LOAD-BEARING: a static on a `View` inherits the type's
    /// MainActor isolation under the macOS 26 SDK, and the Swift Testing suite
    /// that calls this runs on a cooperative thread — the off-main call SIGTRAPs
    /// the whole test process (#4201).
    nonisolated static func canvasNodeIds(forSelection selection: Set<String>) -> Set<String> {
        Set(selection.map { SpatialLibraryProjector.nodeId(forDocument: $0) })
    }

    /// The library selection for a node the user clicked on the canvas. A
    /// non-document node (an entity orb, a standalone canvas item) selects no
    /// document — it has no row in any list mode to select.
    nonisolated static func librarySelection(forCanvasNodeIds nodeIds: Set<String>) -> Set<String> {
        Set(nodeIds.compactMap { SpatialLibraryProjector.documentId(fromNodeId: $0) })
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

    /// The modifiers currently held, translated for `SelectionGrammar`.
    /// `NSEvent.modifierFlags` is the live modifier state, still valid inside a
    /// tap callback; iOS has no equivalent on a tap, so it reports none and the
    /// grammar collapses to plain selection there.
    var currentSelectionModifiers: SelectionGrammar.Modifiers {
        #if os(macOS)
        let flags = NSEvent.modifierFlags
        var modifiers: SelectionGrammar.Modifiers = []
        if flags.contains(.shift) { modifiers.insert(.shift) }
        if flags.contains(.command) { modifiers.insert(.command) }
        return modifiers
        #else
        return []
        #endif
    }

    /// One click, one grammar (#4377).
    ///
    /// This used to be three private methods with their own anchor handling,
    /// and the ⇧ branch silently did NOTHING whenever the anchor was missing or
    /// no longer visible — after a filter change, a re-sort, a columns-mode
    /// switch, or a selection restored from state rather than clicked. That is
    /// why shift-click read as "not enabled". `SelectionGrammar` always returns
    /// a selection; there is no path back to a no-op.
    func handleTap(_ doc: Document) {
        onRequestFocus()
        let result = SelectionGrammar.click(
            id: doc.id,
            in: keyboardNavigationDocuments.map(\.id),
            selection: selection,
            anchor: selectionAnchor,
            modifiers: currentSelectionModifiers
        )
        apply(result)

        // The preview follows the row you just acted on — unless the click
        // DESELECTED it, in which case previewing it would contradict the
        // selection.
        if result.selection.contains(doc.id) {
            detailDocument = doc
        }

        // Drill-in is a PLAIN-click behaviour only: a ⇧ or ⌘ click is building
        // a selection, and navigating away mid-build would throw it out.
        guard currentSelectionModifiers.isEmpty else { return }
        if Self.plainTapNavigatesInto(
            isNavigableContainer: canNavigateInto(doc),
            sidebarHidden: sidebarHidden,
            isCompactWidth: horizontalSizeClass == .compact
        ) {
            onNavigateInto(doc)
        }
    }

    /// Commit a grammar result to the three pieces of selection state, which
    /// always move together.
    func apply(_ result: SelectionGrammar.Result) {
        selection = result.selection
        selectionAnchor = result.anchor
        selectionCursor = result.cursor
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

    /// The entity browser reads the SAME grammar over its own ordered ids —
    /// one rulebook, two lists (#4377).
    func handleEntityTap(_ entity: Components.Schemas.KnowledgeEntity) {
        onRequestFocus()
        apply(SelectionGrammar.click(
            id: entitySelectionId(for: entity),
            in: filteredEntities.map { entitySelectionId(for: $0) },
            selection: selection,
            anchor: selectionAnchor,
            modifiers: currentSelectionModifiers
        ))
        focusEntityIfPossible(entity)
    }

    func handleEntityDoubleClick(_ entity: Components.Schemas.KnowledgeEntity) {
        let entityId = entitySelectionId(for: entity)
        withAnimation(.easeInOut(duration: 0.2)) {
            apply(SelectionGrammar.click(
                id: entityId,
                in: filteredEntities.map { entitySelectionId(for: $0) },
                selection: selection,
                anchor: selectionAnchor,
                modifiers: []
            ))
        }
        listScrollCenterTarget = entityId
        focusEntityIfPossible(entity)
    }

    // MARK: - Open Affordances (#1685)

    /// In-window "Open": navigate into containers, otherwise show the doc in
    /// the detail/preview pane. Mirrors the existing double-click open path.
    func openDocument(_ doc: Document) {
        // Opening is a plain selection of one row — cursor included, so the
        // arrows resume from what you just opened rather than from wherever
        // the previous anchor was (#4377).
        apply(SelectionGrammar.select(doc.id))
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
