import OSLog
import SwiftUI

private let cellDropLogger = Logger(
    subsystem: "app.fichero.fichero", category: "LibraryCellDrop"
)

// MARK: - Per-cell folder drop (#4124)
//
// Grid/list/table cells were drag SOURCES only — the sole drop target was the
// whole content pane, so hovering anywhere lit every cell and the drop
// imported into the folder being VIEWED, not the folder under the cursor.
// This modifier gives folder cells a real .dropDestination for in-app item
// drags, with a per-cell highlight, routed through the same move executor
// the sidebar uses (documentStore.moveDocument).

/// Accepts in-app `LibraryItemDrag` payloads on folder cells; non-folders
/// pass through untouched. Per-cell `isTargeted` state = only the hovered
/// folder highlights.
struct LibraryFolderCellDrop: ViewModifier {
    let isFolder: Bool
    let onDropItems: ([LibraryItemDrag]) -> Bool

    @State private var isTargeted = false

    func body(content: Content) -> some View {
        if isFolder {
            content
                .dropDestination(for: LibraryItemDrag.self) { items, _ in
                    onDropItems(items)
                } isTargeted: { targeted in
                    isTargeted = targeted
                }
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(Color.accentColor, lineWidth: 2)
                        .opacity(isTargeted ? 1 : 0)
                        .allowsHitTesting(false)
                )
        } else {
            content
        }
    }
}

extension LibraryView {
    /// Move dragged in-app items into `folder`. Returns whether the drop was
    /// accepted. Self-drops and non-document payloads are rejected up front;
    /// per-item move failures are LOGGED loudly, never swallowed silently.
    func moveDraggedItems(_ items: [LibraryItemDrag], into folder: Document) -> Bool {
        guard folder.docType == .folder else { return false }
        let ids = items.compactMap { drag -> String? in
            switch drag.kind {
            case .document, .page, .group:
                return drag.documentId ?? drag.id
            case .artifact, .note, .annotation:
                return nil
            }
        }
        .filter { $0 != folder.id }
        guard !ids.isEmpty else { return false }

        Task { @MainActor in
            var failures = 0
            for id in ids {
                do {
                    _ = try await documentStore.moveDocument(id, toParent: folder.id)
                } catch {
                    failures += 1
                    cellDropLogger.error(
                        "move \(id, privacy: .public) into \(folder.id, privacy: .public) failed: \(error.localizedDescription)"
                    )
                }
            }
            if failures > 0 {
                cellDropLogger.error("cell drop: \(failures) of \(ids.count) moves failed")
            }
            await documentStore.refresh()
        }
        return true
    }
}
