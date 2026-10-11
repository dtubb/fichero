import SwiftUI

// An empty folder looks like an empty Finder window (Daniel's first launch, 2026-10-11): in the list and table
// modes the table's own column header with its empty striped rows, in icon mode a blank pane, a footer that counts
// what is there ("0 items"), and in the middle the invitation the pane already accepts: drop files or folders here
// to import. The drop itself is the pane's (`LibraryPaneDrop`, the one import-on-drop path), highlighted while a
// drag is over it.

/// What an empty folder's pane says, in words: pure, so a test can read it.
enum LibraryEmptyFolder {
    static let dropHint = "Drop files or folders here to import"

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

/// The invitation in the middle of an empty folder, and the footer under it.
struct LibraryEmptyFolderOverlay: View {
    /// Set Up… for an empty project (`source.onboard.reachable`), as the old empty state offered it.
    var onSetUp: (() -> Void)?

    var body: some View {
        VStack(spacing: 10) {
            Image(systemName: "square.and.arrow.down.on.square")
                .font(.largeTitle)
                .foregroundStyle(.tertiary)
            Text(LibraryEmptyFolder.dropHint)
                .font(.callout)
                .foregroundStyle(.secondary)
            if let onSetUp {
                Button("Set Up…", action: onSetUp)
                    .buttonStyle(.bordered)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("library.emptyFolder.dropHint")
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
    /// An empty folder's pane: the table (list and table modes) or a blank pane (icon mode), the drop invitation
    /// over it, and the count under it.
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
            .overlay { LibraryEmptyFolderOverlay(onSetUp: emptyProjectSetUp) }
            LibraryEmptyFolderFooter(count: 0)
        }
        // Right-click anywhere in it offers the import, as the empty state did (#4449).
        .contextMenu { libraryEmptyAreaImportMenu }
    }

    /// Set Up… for an empty project, as `emptyState` offers it; nil when the project is not one.
    private var emptyProjectSetUp: (() -> Void)? {
        #if os(macOS)
        guard projectOffersSetUp(
            reason: emptyReason,
            isLoaded: libraryManager.loadedLibraryIds.contains(windowState.libraryId),
            rootCollections: documentStore.collections
        ) else { return nil }
        let libraryId = windowState.libraryId
        let manager = libraryManager
        return { manager.requestSetUp(for: libraryId) }
        #else
        return nil
        #endif
    }
}

#Preview("An empty folder: the invitation and the count") {
    VStack(spacing: 0) {
        Color.clear
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .overlay { LibraryEmptyFolderOverlay(onSetUp: {}) }
        LibraryEmptyFolderFooter(count: 0)
    }
    .frame(width: 520, height: 320)
}
