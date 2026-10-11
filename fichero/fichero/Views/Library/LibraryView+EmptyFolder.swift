import SwiftUI

// An empty folder looks like an empty Finder window (Daniel, 2026-10-11, "less is more"): in the list and table
// modes the table's own column header with its empty striped rows, in icon mode a blank pane, and a footer that
// counts what is there ("0 items"). No words in the middle and no button: it is still a drop target, the pane's own
// (`LibraryPaneDrop`, the one import-on-drop path), and its highlight while a drag is over it is all it shows.

/// What an empty folder's pane shows: pure, so a test can read it.
enum LibraryEmptyFolder {
    /// The footer's count, as Finder words it: "0 items", "1 item", "12 items".
    static func footer(count: Int) -> String {
        count == 1 ? "1 item" : "\(count) items"
    }

    /// Whether the empty pane is a folder being browsed, which looks like an empty Finder window; a filtered or
    /// searched-out body, or an entity projection, keeps its own message (`LibraryEmptyReason`).
    static func looksLikeAnEmptyFolder(_ reason: LibraryEmptyReason) -> Bool {
        reason.offersImport
    }

    /// The table's header and stripes stand for the list and table modes; icon mode, and the canvas and the other
    /// modes, are a blank pane.
    static func showsTable(_ mode: ViewDisplayMode) -> Bool {
        mode == .list || mode == .table
    }
}

struct LibraryEmptyFolderFooter: View {
    let count: Int

    var body: some View {
        VStack(spacing: 0) {
            Divider()
            Text(LibraryEmptyFolder.footer(count: count))
                .font(.caption)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 4)
                .accessibilityIdentifier("library.emptyFolder.footer")
        }
    }
}

extension LibraryView {
    /// An empty folder's pane: the table (list and table modes) or a blank pane (icon mode), and the count under it.
    @ViewBuilder
    var emptyFolderView: some View {
        VStack(spacing: 0) {
            Group {
                if LibraryEmptyFolder.showsTable(displayMode) {
                    tableView
                } else {
                    Color.clear
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            LibraryEmptyFolderFooter(count: 0)
        }
        // Right-click anywhere in it offers the import, as the empty state did (#4449).
        .contextMenu { libraryEmptyAreaImportMenu }
    }
}

#Preview("An empty folder: blank, with its count") {
    VStack(spacing: 0) {
        Color.clear
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        LibraryEmptyFolderFooter(count: 0)
    }
    .frame(width: 520, height: 320)
}
