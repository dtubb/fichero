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

    @Environment(DocumentStore.self) private var documentStore
    @Environment(LibraryManager.self) private var libraryManager
    @Environment(WindowState.self) private var windowState
    @State private var items: [Document] = []
    /// Each subfolder's own items, for its card (names and pictures, 2026-10-11).
    @State private var contents: [String: [Document]] = [:]
    @State private var selectedNodeIds: Set<String> = []
    @Environment(\.onFolderCanvasFocus) private var onFolderCanvasFocus
    @Environment(\.onFolderCanvasSelection) private var onFolderCanvasSelection
    /// The strip's Colour by, the same key the library's Canvas reads.
    @AppStorage(CanvasColourBy.storageKey) private var colourByRaw = CanvasColourBy.off.rawValue

    var body: some View {
        Group {
            if !items.isEmpty, let library = libraryManager.getLibrary(id: windowState.libraryId) {
                // The library's own canvas, fed by the library's own board builder (`CanvasBoard`,
                // `library.canvas.one-canvas-everywhere`): the same cards, groups, drop-into
                // containers and colouring the library's Canvas mode builds from these documents.
                let folderBoard = board
                CanvasSceneView(
                    nodes: folderBoard.projection.nodes,
                    connections: [],
                    selectedNodeIds: $selectedNodeIds,
                    layoutStore: library.canvasLayoutStore,
                    itemStore: library.canvasItemStore,
                    folderScopeId: folderId,
                    // Double-click a card: the Preview shows that item.
                    onOpenDocument: { onNavigateToDocument?($0) },
                    containerIds: folderBoard.containerIds,
                    moveIntoContainer: { [documentStore] in
                        CanvasBoard.moveIntoContainer($0, $1, using: documentStore)
                    },
                    storageService: library.storageService,
                    tint: CanvasBoard.tint(of: items, by: CanvasColourBy.stored(colourByRaw)),
                    faces: folderBoard.faces,
                    // A folder of groups shows each as a frame holding its pages (#5570).
                    groupNodeIds: folderBoard.groupNodeIds,
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
            } else {
                // Empty means empty (Daniel, 2026-10-11): an empty folder or group previews as a blank pane, no
                // glyph and no sentence, as the Items pane and the Trash do. The same quiet frame holds while the
                // children resolve, so nothing flashes either way (★ EVERY FRAME PERFECT).
                Color.clear
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .task(id: folderId) {
            // Every child, subfolders included, as the library's Canvas shows them.
            items = await documentStore.children(of: folderId)
            // Then what each subfolder holds, so its card shows it; the cards are drawn first and fill in.
            var held: [String: [Document]] = [:]
            for folder in items where folder.docType == .folder {
                held[folder.id] = await documentStore.children(of: folder.id)
            }
            contents = held
        }
    }

    /// This folder's board, from the library canvas's one builder.
    private var board: CanvasBoard {
        CanvasBoard.of(documents: items, contents: contents)
    }
}
