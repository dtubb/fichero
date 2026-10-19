import SwiftUI

// An empty folder is a blank pane (Daniel, 2026-10-11, "less is more"; his 2026-10-19 test of the table's header and
// grey rows over it: none, #5826) with a footer that counts what is there ("0 items"). A finished load with nothing
// draws no placeholder rows. No words in the middle and no button: it is still a drop target, the pane's own
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

    /// Whether the empty pane draws the table's header and empty rows: never, in any mode (#5826).
    static func showsTable(_ mode: ViewDisplayMode) -> Bool { false }
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
    /// An empty folder's pane: blank, and the count under it.
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
