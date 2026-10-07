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
extension EnvironmentValues {
    /// Where a folder's canvas in the Preview reports the ONE card selected on it (nil for none or
    /// several), so the Inspector and the Reader show that item while the Preview keeps the board
    /// (2026-09-30, #5305). Set by ContentView on the Preview pane.
    @Entry var onFolderCanvasFocus: ((Document?) -> Void)?
    /// Every card selected on that canvas, so Group (⌥⌘G) can gather them (#5303).
    @Entry var onFolderCanvasSelection: (([Document]) -> Void)?
}

struct FolderContentsPreview: View {
    let folderId: String
    var onNavigateToDocument: ((String) -> Void)?
    /// A group previews here too, as its pages on its own board (#5570); only its empty state
    /// differs.
    var isGroup = false

    @Environment(DocumentStore.self) private var documentStore
    @Environment(LibraryManager.self) private var libraryManager
    @Environment(WindowState.self) private var windowState
    @State private var items: [Document] = []
    @State private var loaded = false
    @State private var selectedNodeIds: Set<String> = []
    @Environment(\.onFolderCanvasFocus) private var onFolderCanvasFocus
    @Environment(\.onFolderCanvasSelection) private var onFolderCanvasSelection
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
                    // Double-click a card: the Preview shows that item.
                    onOpenDocument: { onNavigateToDocument?($0) },
                    storageService: library.storageService,
                    tint: tint,
                    // A folder of groups shows each as a frame holding its pages (#5570).
                    groupNodeIds: CanvasGroupNesting.groupNodeIds(in: items),
                    pagesOfGroup: { [documentStore] nodeId in
                        await documentStore.canvasPageNodes(ofGroupNode: nodeId)
                    }
                )
                .overlay(alignment: .topTrailing) {
                    CanvasControlStrip()
                        .padding(8)
                }
                .onChange(of: selectedNodeIds) { _, ids in
                    let focused = ids.count == 1
                        ? ids.first.flatMap(SpatialLibraryProjector.documentId(fromNodeId:))
                            .flatMap { id in items.first { $0.id == id } }
                        : nil
                    onFolderCanvasFocus?(focused)
                    onFolderCanvasSelection?(ids.compactMap(SpatialLibraryProjector.documentId(fromNodeId:))
                        .compactMap { id in items.first { $0.id == id } })
                }
                .onDisappear {
                    onFolderCanvasFocus?(nil)
                    onFolderCanvasSelection?([])
                }
            } else if loaded {
                if isGroup {
                    ContentUnavailableView(
                        "Empty Group",
                        systemImage: DocType.group.icon,
                        description: Text("This group holds no pages.")
                    )
                } else {
                    ContentUnavailableView(
                        "Empty Folder",
                        systemImage: "folder",
                        description: Text("Items you add to this folder appear here.")
                    )
                }
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
