import FicheroAPIClient
import SwiftUI

// MARK: - Whole-mode preview fixtures (Daniel, 2026-08-09: "did you get all
// library views having previews in xcode so you can look at them there?")
//
// LibraryView reads NINE non-optional environment objects — the boundary
// crash class — so a bare `LibraryView` preview traps on first body
// evaluation (both old previews did, for months). This is the ONE fixture
// environment: every object constructed inert against a nil-path client, no
// network, no engine. Every mode preview and LibraryView's own previews go
// through it; add new required objects HERE and every canvas keeps working.

enum LibraryPreviewFixtures {
    /// One inert library whose FULL service set backs every canvas — built
    /// once so all previews in a canvas session share it.
    @MainActor
    static let library = LibraryManager.LibraryReference(
        url: FileManager.default.temporaryDirectory.appendingPathComponent("fichero-preview-library"),
        document: FicheroDocument(),
        displayName: "Preview"
    )

    @MainActor
    static func environment<V: View>(_ view: V) -> some View {
        view
            // The ONE service list (LibraryServiceEnvironment) — hand-picking
            // objects here crashed the Columns canvas the moment its trailing
            // preview column mounted EditorView, which reads services the
            // hand-picked nine didn't include (2026-08-09 SIGTRAP in
            // EnvironmentValues.subscript). The shared list is the fix AND
            // the regression guard: services added there reach previews too.
            .libraryServiceEnvironment(library)
            .environment(AppState())
            .environment(LibraryManager.shared)
            .environment(WindowState(libraryId: library.id))
            .environment(WorkflowExecutionObserver())
            .environment(KGFocusState())
    }

    static let documents: [Document] = [
        Document(id: "folder-1", docType: .folder, name: "Letters 1893", childCount: 4),
        Document(id: "pdf-1", docType: .file, fileType: .pdf, name: "Diary.pdf", childCount: 3),
        Document(id: "page-1", parentId: "pdf-1", docType: .page, name: "Page 1", sequence: 1),
        Document(id: "page-2", parentId: "pdf-1", docType: .page, name: "Page 2", sequence: 2),
        Document(
            id: "text-1", docType: .file, fileType: .text, name: "Field notes.md",
            pageContent: "Rain again. The archive closes at noon."
        ),
        Document(id: "img-1", docType: .file, fileType: .image, name: "scan_001.tif")
    ]

    @MainActor
    static func mode(_ displayMode: ViewDisplayMode, _ layout: LibraryLayout) -> some View {
        environment(
            LibraryView(
                documents: documents,
                contentCollection: .documents,
                isLoading: false,
                isConnected: true,
                errorMessage: nil,
                onRetry: {},
                libraryToolbar: LibraryToolbarState(),
                selection: .constant(["pdf-1"]),
                detailDocument: .constant(nil),
                viewMode: .constant(layout),
                isPaneFocused: true,
                displayMode: displayMode,
                folderId: nil
            )
        )
        .frame(width: 760, height: 480)
    }
}

#Preview("Icon mode") { LibraryPreviewFixtures.mode(.icon, .icons) }
#Preview("List mode") { LibraryPreviewFixtures.mode(.list, .list) }
#Preview("Table mode") { LibraryPreviewFixtures.mode(.table, .table) }
#Preview("Columns mode") { LibraryPreviewFixtures.mode(.columns, .columns) }
