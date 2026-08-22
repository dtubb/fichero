import FicheroAPIClient
import SwiftUI

// MARK: - Canvas & spatial view modes (#4192)

extension Notification.Name {
    /// Toggle zoom-to-card in whichever canvas is showing. `object` is the
    /// spatial node id ("doc:<uuid>").
    static let canvasFocusZoomToggle = Notification.Name("canvasFocusZoomToggle")
}

/// The two spatial view modes and the audited move their drags perform.
///
/// Split out of `LibraryView` for `type_body_length`, which #4353's strict
/// tier treats as an error rather than a warning. Chosen by COHESION, not line
/// count: these three are the only members that speak `SpatialNode` ids.
///
/// The two view modes became internal in the move — `private` is FILE-scoped
/// and `libraryRowsOrEmptyState` still selects between them from the main
/// file. `moveCanvasNodeIntoContainer` stays private: both of its callers came
/// with it.
extension LibraryView {
    /// Move a dragged canvas node INTO a container via the audited `document.move`
    /// action (#3086). Maps spatial node ids → document ids; a non-document drag
    /// (canvas item) has no `doc:` id and is a safe no-op. The change stream
    /// reconciles both windows; a failure leaves the row put (never silent-drops).
    private func moveCanvasNodeIntoContainer(_ nodeId: String, _ containerNodeId: String) {
        guard let docId = SpatialLibraryProjector.documentId(fromNodeId: nodeId),
              let parentId = SpatialLibraryProjector.documentId(fromNodeId: containerNodeId) else { return }
        Task { @MainActor in
            _ = try? await documentStore.moveDocument(docId, toParent: parentId)
        }
    }
    /// The document behind the canvas selection's primary node — the subject
    /// of the right-click menu (user, 2026-08-20: "in 2d and 3d and all
    /// other library views we ought to be able to do contextual menus").
    /// `documentContextMenu`'s own Finder-rule resolvers widen to the full
    /// selection exactly as the list/grid menus do, because the canvas
    /// selection IS `selection` (one mapped binding).
    private var canvasMenuDocument: Document? {
        // No `?? selection.first` fallback: a selection whose primary cannot
        // be named by row order gets the empty menu, never an arbitrary node
        // (selection-grammar rule 2, 2026-08-09).
        guard let firstId = shellPrimarySelectionId(
            in: selection, orderedBy: filteredDocuments
        ) else { return nil }
        return documents.first { $0.id == firstId }
            ?? filteredDocuments.first { $0.id == firstId }
    }

    @ViewBuilder
    private func canvasContextMenu() -> some View {
        if let doc = canvasMenuDocument {
            // Touch-reachable twin of the canvas double-click (iPad has no
            // double-click; the guardrail is right that the action must
            // exist on a reachable route). Same toggle, same return trip.
            Button("Zoom to Card") {
                NotificationCenter.default.post(
                    name: .canvasFocusZoomToggle, object: "doc:\(doc.id)"
                )
            }
            Divider()
            documentContextMenu(for: doc)
        } else {
            Text("Select a card for its actions")
        }
    }

    @ViewBuilder
    var spaceModeView: some View {
        if featureManager.isCanvasRealityKit3DEnabled {
            CanvasSpaceView(
                nodes: libraryProjection.nodes,
                connections: [],
                selectedNodeIds: canvasSelectedNodeIds,
                layoutStore: canvasLayoutStore,
                storageService: activeLibraryReference?.storageService,
                itemStore: canvasItemStore,
                folderScopeId: folderId ?? wholeLibraryRoomId,
                containerIds: canvasContainerIds,
                moveIntoContainer: moveCanvasNodeIntoContainer
            )
            .contextMenu { canvasContextMenu() }
        } else {
            SpaceSceneView(
                nodes: libraryProjection.nodes,
                connections: [],
                selectedNodeIds: canvasSelectedNodeIds,
                layoutStore: canvasLayoutStore,
                itemStore: canvasItemStore,
                folderScopeId: folderId ?? wholeLibraryRoomId,
                // #4160: textures must fetch through THIS library's storage —
                // the cache previously always used the global library, so any
                // non-global library rendered colored placeholders instead of
                // page thumbnails.
                storageService: activeLibraryReference?.storageService
            )
            .contextMenu { canvasContextMenu() }
        }
    }
    /// The 2D Canvas renderer, gated (#3083): the new RealityKit-ortho
    /// `CanvasSceneView` when the flag is on, else the SwiftUI `Spatial2DCanvas`.
    /// Both read the SAME shared stores, so switching engines is transparent;
    /// the SwiftUI canvas is retired only at cutover (#3087). Extracted to keep
    /// `libraryContent`'s switch within the type-checker budget.
    @ViewBuilder
    var canvasModeView: some View {
        if featureManager.isCanvasRealityKit2DEnabled {
            CanvasSceneView(
                nodes: libraryProjection.nodes,
                connections: [],
                selectedNodeIds: canvasSelectedNodeIds,
                layoutStore: canvasLayoutStore,
                itemStore: canvasItemStore,
                folderScopeId: folderId ?? wholeLibraryRoomId,
                containerIds: canvasContainerIds,
                moveIntoContainer: moveCanvasNodeIntoContainer,
                storageService: activeLibraryReference?.storageService
            )
            .contextMenu { canvasContextMenu() }
        } else {
            Spatial2DCanvas(
                nodes: libraryProjection.nodes,
                connections: [],
                selectedNodeIds: canvasSelectedNodeIds,
                layoutStore: canvasLayoutStore,
                itemStore: canvasItemStore,
                folderScopeId: folderId ?? wholeLibraryRoomId,
                storageService: activeLibraryReference?.storageService
            )
            .contextMenu { canvasContextMenu() }
        }
    }
}
