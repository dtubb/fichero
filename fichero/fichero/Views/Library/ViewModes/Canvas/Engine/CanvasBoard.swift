import Foundation

// MARK: - One board, one model, every host (`library.canvas.one-canvas-everywhere`)

/// What a canvas host hands `CanvasSceneView` (or `CanvasSpaceView`) about a set of documents: the
/// cards, which of them are groups (frames holding their pages, #5570), which are containers a card
/// can be dropped into (#3086), and their colouring (§20.3 Colour by).
///
/// Ruled 2026-10-09: the folder canvas in the Preview and the Canvas and Space modes in the Library
/// are ONE canvas: the same view, the same renderer, the same cards, the same selection, drag,
/// never-move rule and menus. Before this each host built these inputs its own way (the Preview
/// passed no containers, so a card could not be dropped into a subfolder there), which is how two
/// hosts of one view drift into two canvases. Both hosts build them here.
struct CanvasBoard: Equatable {
    /// The cards and their links, through the library canvas's one projector.
    let projection: SpatialLibraryProjection
    /// Group documents on the board, as node ids.
    let groupNodeIds: Set<String>
    /// Folder and workspace documents on the board, as node ids: dropping a card onto one moves
    /// the card's document into it.
    let containerIds: Set<String>

    /// The board for `documents` (and, for the library's whole-board canvas, its `entities`).
    static func of(
        documents: [Document], entities: [SpatialLibraryInput.Entity] = []
    ) -> CanvasBoard {
        CanvasBoard(
            projection: SpatialLibraryProjector.project(
                SpatialLibraryInput(
                    documents: documents.map {
                        SpatialLibraryInput.Document(id: $0.id, name: $0.name, parentId: $0.parentId)
                    },
                    entities: entities,
                    claims: []
                )
            ),
            groupNodeIds: CanvasGroupNesting.groupNodeIds(in: documents),
            containerIds: containerIds(in: documents)
        )
    }

    /// Folder and workspace documents among `documents`, as node ids.
    static func containerIds(in documents: [Document]) -> Set<String> {
        Set(
            documents.filter { $0.docType == .folder || $0.isWorkspace }
                .map { SpatialLibraryProjector.nodeId(forDocument: $0.id) }
        )
    }

    /// Move a card's document into the container it was dropped onto, through the audited
    /// `document.move` (#3086). Not a document (a canvas item), or not a container: nothing happens.
    static func moveIntoContainer(_ nodeId: String, _ containerNodeId: String, using store: DocumentStore) {
        guard let docId = SpatialLibraryProjector.documentId(fromNodeId: nodeId),
              let parentId = SpatialLibraryProjector.documentId(fromNodeId: containerNodeId) else { return }
        Task { @MainActor in
            _ = try? await store.moveDocument(docId, toParent: parentId)
        }
    }

    /// The colouring of `documents` under `mode`, by node id. Both hosts colour this way.
    static func tint(of documents: [Document], by mode: CanvasColourBy) -> CanvasTint {
        guard mode != .off else { return .neutral }
        let values = documents.reduce(into: [String: String]()) { map, document in
            guard let value = mode.value(for: document) else { return }
            map[SpatialLibraryProjector.nodeId(forDocument: document.id)] = value
        }
        return CanvasTint.byValue(values)
    }
}
