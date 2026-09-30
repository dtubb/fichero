import SwiftUI

/// A selected plain folder previews as its own 2D canvas (#5300, `library.canvas.a-folder-previews-as-its-canvas`).
///
/// It used to preview its FIRST item as though the folder were a PDF (#25), and the Inspector,
/// the Segments pane and the Reader followed that first item (#5204, #5205): select a folder and
/// three panes described one file inside it. Now the folder is what every pane shows, and the
/// Preview draws its items as cards on the SAME canvas the library's Canvas mode draws for that
/// folder: one layout per folder, one write path, so a card moved here is moved there too (#5301),
/// and *Arrange by* lays them out (#5302). A click selects a card and a drag moves it (maintainer,
/// 2026-09-30); a click does not leave the board, or a drag could never start.
struct FolderContentsPreview: View {
    let folderId: String
    var onNavigateToDocument: ((String) -> Void)?

    @Environment(DocumentStore.self) private var documentStore
    @Environment(LibraryManager.self) private var libraryManager
    @Environment(WindowState.self) private var windowState
    @State private var items: [Document] = []
    @State private var loaded = false
    @State private var selectedNodeIds: Set<String> = []
    /// The strip's Colour by, the same key the library's Canvas reads.
    @AppStorage(CanvasColourBy.storageKey) private var colourByRaw = CanvasColourBy.off.rawValue

    var body: some View {
        Group {
            if !items.isEmpty, let library = libraryManager.getLibrary(id: windowState.libraryId) {
                CanvasSceneView(
                    nodes: projection.nodes,
                    connections: [],
                    selectedNodeIds: $selectedNodeIds,
                    layoutStore: library.canvasLayoutStore,
                    itemStore: library.canvasItemStore,
                    folderScopeId: folderId,
                    storageService: library.storageService,
                    tint: tint
                )
                .overlay(alignment: .topTrailing) {
                    CanvasControlStrip()
                        .padding(8)
                }
            } else if loaded {
                ContentUnavailableView(
                    "Empty Folder",
                    systemImage: "folder",
                    description: Text("Items you add to this folder appear here.")
                )
            } else {
                // ★ EVERY FRAME PERFECT: hold a quiet frame while the cached
                // children resolve (usually one turn) instead of flashing the
                // empty-folder state first.
                Color.clear
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .task(id: folderId) {
            // Every child, subfolders included, as the library's Canvas shows them.
            items = await documentStore.children(of: folderId)
            loaded = true
        }
    }

    /// Colour by, from this folder's items, as the library's Canvas computes it (`canvasTint`).
    private var tint: CanvasTint {
        let mode = CanvasColourBy.stored(colourByRaw)
        guard mode != .off else { return .neutral }
        let values = items.reduce(into: [String: String]()) { map, document in
            guard let value = mode.value(for: document) else { return }
            map[SpatialLibraryProjector.nodeId(forDocument: document.id)] = value
        }
        return CanvasTint.byValue(values)
    }

    /// The folder's items as canvas cards, through the library Canvas's own projector.
    private var projection: SpatialLibraryProjection {
        SpatialLibraryProjector.project(
            SpatialLibraryInput(
                documents: items.map { SpatialLibraryInput.Document(id: $0.id, name: $0.name, parentId: $0.parentId) },
                entities: [],
                claims: []
            )
        )
    }
}
