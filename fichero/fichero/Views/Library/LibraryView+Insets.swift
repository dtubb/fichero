import Combine
import FicheroAPIClient
import SwiftUI

// MARK: - Connection error + bottom inset (#3160: kept out of the type body)
extension LibraryView {
    // Sort field / direction / filter-bar visibility now live on the shared
    // store (#1477). These computed forwarders keep the existing call sites and
    // `$`-bindings working unchanged.
    var sortFieldRaw: String {
        get { libraryToolbar.sortFieldRaw }
        nonmutating set { libraryToolbar.sortFieldRaw = newValue }
    }

    var sortAscending: Bool {
        get { libraryToolbar.sortAscending }
        nonmutating set { libraryToolbar.sortAscending = newValue }
    }

    var showFilterBar: Bool {
        get { libraryToolbar.showFilterBar }
        nonmutating set { libraryToolbar.showFilterBar = newValue }
    }

    var sortField: LibrarySortField { libraryToolbar.sortField }

    // internal (not private): accessed from LibraryView+DisplayModes extension (separate file)
    var scopedLibraryReference: LibraryManager.LibraryReference? {
        libraryManager.getLibrary(id: windowState.libraryId)
    }

    // Internal, not private: the columns extension (seedColumnsPathFromSelection)
    // resolves ancestry through the same reference.
    var libraryReference: LibraryManager.LibraryReference? {
        libraryManager.getLibrary(id: windowState.libraryId) ?? libraryManager.globalLibrary
    }

    /// Canvas stores are shared per library (#3082), but must never silently
    /// swap to another library's client/scope while this window's library is
    /// still loading or unavailable (#3198).
    /// Promoted `private` → internal: read from `LibraryView+CanvasModes.swift`
    /// after the #4353 file split, and `private` is file-scoped.
    var canvasLayoutStore: CanvasLayoutStore? { scopedLibraryReference?.canvasLayoutStore }
    var canvasItemStore: CanvasItemStore? { scopedLibraryReference?.canvasItemStore }

    /// Extracted from `.focusedSceneValue` so the Swift type-checker doesn't
    /// time out on the inline ternary-with-closure expression. Wrapped in
    /// `FocusedLibraryAction` (Equatable, keyed on `isEnabled` only) so the
    /// focus system short-circuits across body passes — publishing a raw
    /// closure here caused an AttributeGraph invalidation storm on launch
    /// whenever a persisted selection restored (hang / AG compare crash).
    var runWorkflowOnSelectionAction: FocusedLibraryAction? {
        guard !isShowingEntitiesCollection, !selection.isEmpty,
              featureManager.isWorkflowRunOnSelectionEnabled else { return nil }
        return FocusedLibraryAction(isEnabled: true) {
            selectedDocumentIdsForBatch = Array(selection)
            showWorkflowPicker = true
        }
    }

    func refreshPendingStatusesFromLiveUpdate() {
        guard hasProcessingDocuments, let parentId = folderId else { return }
        Task { await documentStore.refreshPendingStatusesOnly(in: parentId) }
    }

    /// Shown for a load that failed because the engine was unreachable
    /// (`isEngineOutage`) or because the engine itself is in a failure phase —
    /// never for a library that simply hasn't loaded yet.
    ///
    /// The sentence comes from `ConnectionPresentation` (#4380), the same
    /// mapping the engine popover reads, so the two surfaces cannot describe
    /// one failure two different ways. A raw transport error never reaches
    /// this pane (#4269); it lives in the engine log.
    func connectionErrorState(message: String) -> some View {
        VStack(spacing: 16) {
            Image(systemName: "wifi.slash")
                .font(.largeTitle)
                .foregroundColor(.secondary)

            Text("Can't Reach the Server")
                .font(.title2)
                .fontWeight(.semibold)
                // #3937's assertion target: this claims an outage, so a UI test
                // has to be able to catch it claiming one on a healthy engine.
                .accessibilityIdentifier("library.outage")

            Text(message)
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 400)

            Button("Try Again") {
                onRetry()
            }
            .keyboardShortcut("r", modifiers: .command)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    /// The honest sentence for the CURRENT engine phase, or nil when the engine
    /// is not in a failure phase at all (#4372). Non-nil is what promotes the
    /// pane from "loading" to "the error affordance".
    var engineFailureDetail: String? {
        switch appState.engine.phase {
        case .portConflict, .authRejected, .unreachable, .failed:
            return engineStatusDetail
        case .setupNeeded, .starting, .ready:
            return nil
        }
    }

    /// The sentence for a store load that failed with `engineUnreachable` while
    /// the session itself has not (yet) flipped to a failure phase.
    // Promoted private -> internal: LibraryView.swift file-length split (2026-08-13).
    var engineUnreachableDetail: String {
        ConnectionPresentation.failureDetail(
            accessError: .engineUnreachable,
            authBroken: false,
            ownership: ConnectionPresentation.EngineOwnership.current()
        )
    }

}
// MARK: - Bottom inset (extension, not the struct body — the 250-line
// type_body ratchet; struct body is for state + body only)
extension LibraryView {
    /// Everything stacked below the library's rows, in ONE inset with an
    /// explicit order (#4424).
    ///
    /// It used to be two separate `.safeAreaInset(edge: .bottom)` modifiers —
    /// the mini toolbar added by #4407, then this one. SwiftUI applies insets
    /// outward in modifier order, so the later one lands FURTHEST from the
    /// content: the window-scoped status row ended up beneath the pane-scoped
    /// mini toolbar, which says the opposite of what is true about their
    /// scopes. Two bottom insets is two orderings competing; one inset with a
    /// stated order cannot drift.
    ///
    /// Order, content outward:
    ///   1. the library's mini toolbar — pane-scoped, so nearest its rows
    ///   2. the quick-filter row it reveals
    ///   3. the bottom action/status bar — the outermost thing, beneath all of it
    var bottomInsetContent: some View {
        VStack(spacing: 0) {
            if Self.miniToolbarPlacement == .bottom {
                PaneFilterBar(placement: .bottom) { libraryMiniToolbar }
            }
            if featureManager.isLibraryFilterToolbarEnabled && showFilterBar {
                filterBarView
            }
            libraryBottomActionBar
            // Finder's path bar + status line, scoped to THIS pane (Daniel
            // #106-108: "we want the status bar just on the library" — the
            // old window-wide detailStatusPathBar spanned every pane).
            LibraryPathStatusBar(
                crumbs: libraryPathCrumbs(
                    anchorId: pathBarAnchorId,
                    resolve: { documentStore.resolveDocument($0) }
                ),
                statusText: libraryStatusText(
                    selectionCount: selection.count,
                    itemCount: isShowingEntitiesCollection
                        ? filteredEntities.count : filteredDocuments.count
                ),
                onNavigate: { doc in onNavigateInto(doc) }
            )
        }
    }

    /// What the path bar's trailing crumb anchors on: the document-order
    /// primary selection when there is one, else the browsed folder.
    /// `folderId` is the sidebar item id, which prefixes documents "doc:".
    private var pathBarAnchorId: String? {
        if let primary = orderedPrimarySelectionId { return primary }
        guard let folderId else { return nil }
        return folderId.hasPrefix("doc:") ? String(folderId.dropFirst(4)) : folderId
    }
}

// MARK: - Spatial projection

extension LibraryView {
    /// The spatial projection only feeds the `.canvas` / `.space` canvases, so
    /// mapping every document + entity through `SpatialLibraryProjector` on each
    /// documentStore/entity change is wasted work in icon/list/table (#3867).
    static func usesSpatialProjection(_ mode: ViewDisplayMode) -> Bool {
        switch mode {
        case .canvas, .space, .workspace: return true
        // The Data mode reads the dataset query, not the spatial projection.
        case .icon, .list, .table, .columns, .grid, .cards, .timeline, .calendar, .geoMap: return false
        }
    }

    // Promoted private -> internal: LibraryView.swift file-length split (2026-08-13).
    func refreshLibraryProjection() {
        // Skip the full documents+entities map unless a spatial canvas is shown.
        // Recomputed lazily on switch INTO canvas/space (see onChange(displayMode)).
        guard Self.usesSpatialProjection(displayMode) else { return }
        cachedLibraryProjection = SpatialLibraryProjector.project(
            SpatialLibraryInput(
                documents: documents.map {
                    SpatialLibraryInput.Document(id: $0.id, name: $0.name, parentId: $0.parentId)
                },
                entities: entities.compactMap { entity in
                    guard let id = entity.id else { return nil }
                    return SpatialLibraryInput.Entity(
                        id: id,
                        canonicalName: entity.canonicalName,
                        entityType: entity.entityType?.rawValue
                    )
                },
                claims: []
            )
        )
    }

    /// Projects the current documents + entities into spatial nodes/links for
    /// the `.canvas` (and future `.space`) views. Item positions are persisted
    /// separately via `CanvasLayoutStore` (#2293); this only supplies the
    /// projector's computed defaults.
    var libraryProjection: SpatialLibraryProjection {
        cachedLibraryProjection
    }
}

// MARK: - Kept out of the type body (type_body_length, mirrors #3160)

private extension LibraryView {
    // Processing poller (#518): if any visible docs are still processing, keep
    // a lightweight 15s refresh running so statuses advance to completed even
    // if a backend completion signal is missed.
    private var hasProcessingDocuments: Bool {
        documents.contains { $0.status == .processing || $0.status == .pending }
    }

}

// Moved OUT of the `private extension` above, not merely un-marked: a member's
// own access modifier cannot exceed its enclosing extension's, so dropping
// `private` from the property left it fileprivate and still unreachable from
// `LibraryView+CanvasModes.swift` after the #4353 split.
extension LibraryView {
    /// Spatial node ids of container documents (folder / workspace) — drag-onto
    /// move-into targets (#3086). Dropping onto one moves the dragged doc inside.
    var canvasContainerIds: Set<String> {
        Set(
            documentStore.collections
                .filter { $0.docType == .folder || $0.isWorkspace }
                .map { SpatialLibraryProjector.nodeId(forDocument: $0.id) }
        )
    }
}

// MARK: - Previews

// Both previews go through LibraryPreviewFixtures.environment (2026-08-09):
// LibraryView reads nine non-optional environment objects, and injecting
// only ArtifactService made BOTH of these trap on first body evaluation —
// the boundary crash class, shipped in the previews themselves.

#Preview("Empty") {
    LibraryPreviewFixtures.environment(
        LibraryView(
            documents: [],
            contentCollection: .documents,
            isLoading: false,
            isConnected: true,
            errorMessage: nil,
            onRetry: {},
            libraryToolbar: LibraryToolbarState(),
            selection: .constant(Set<String>()),
            detailDocument: .constant(nil),
            viewMode: .constant(.icons),
            displayMode: .icon,
            folderId: nil
        )
    )
    .frame(width: 600, height: 500)
}

#Preview("Disconnected") {
    LibraryPreviewFixtures.environment(
        LibraryView(
            documents: [],
            contentCollection: .documents,
            isLoading: false,
            isConnected: false,
            errorMessage: nil,
            onRetry: {},
            libraryToolbar: LibraryToolbarState(),
            selection: .constant(Set<String>()),
            detailDocument: .constant(nil),
            viewMode: .constant(.icons),
            displayMode: .icon,
            folderId: nil
        )
    )
    .frame(width: 600, height: 500)
}
