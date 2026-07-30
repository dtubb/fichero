import FicheroAPIClient
import SwiftUI

// MARK: - Canvas & spatial view modes (#4192)

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
    @ViewBuilder
    var spaceModeView: some View {
        if featureManager.isCanvasRealityKit3DEnabled {
            CanvasSpaceView(
                nodes: libraryProjection.nodes,
                connections: [],
                selectedNodeIds: canvasSelectedNodeIds,
                layoutStore: canvasLayoutStore,
                itemStore: canvasItemStore,
                folderScopeId: folderId ?? wholeLibraryRoomId,
                containerIds: canvasContainerIds,
                moveIntoContainer: moveCanvasNodeIntoContainer
            )
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
                moveIntoContainer: moveCanvasNodeIntoContainer
            )
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
        }
    }
}
