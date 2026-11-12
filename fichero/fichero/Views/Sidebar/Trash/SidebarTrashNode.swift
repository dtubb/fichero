import SwiftUI

/// The Trash as a plain folder in the tree (`safety.trash.is-a-folder-in-the-sidebar`, owner design 2026-11-05): the Trash
/// row with a chevron on its leading edge (#6536) that opens what is in it as rows beneath, each with Put Back on its menu.
/// The row itself still opens the Trash pane (`SidebarDestination.trash`), where Put Back and Empty Trash work on a selection.
struct SidebarTrashNode: View {
    /// The most children drawn under the row; the rest are one "more in the Trash" row, since the pane lists them all.
    nonisolated static let childLimit = 50

    /// The entries drawn under the row and how many are left to the pane.
    nonisolated static func shown(_ entries: [TrashEntry], limit: Int = childLimit) -> (entries: [TrashEntry], hidden: Int) {
        (Array(entries.prefix(limit)), max(0, entries.count - limit))
    }

    let store: TrashStore
    let libraryId: UUID
    var isSelected = false
    var onDropIds: (([String]) -> Void)?
    /// Selects the Trash row, so its pane shows.
    var onOpen: () -> Void = {}
    @State private var isExpanded = false

    /// Whether the Trash row opens: only while it holds something, as a folder with children does.
    nonisolated static func opens(isEmpty: Bool) -> Bool { !isEmpty }

    /// A real disclosure group, so the List draws the chevron on the leading edge and indents the children, as for every
    /// folder (owner ruling 2026-11-11, #6536); it was a button at the row's trailing edge, with the children indented by
    /// hand. The tag sits on the group, not inside its label: the List reads the selection from the row itself.
    var body: some View {
        Group {
            if Self.opens(isEmpty: store.isEmpty) {
                DisclosureGroup(isExpanded: $isExpanded) {
                    children
                } label: {
                    row
                }
            } else {
                row
            }
        }
        .tag(SidebarDestination.trash(libraryId: libraryId))
    }

    private var row: some View {
        SidebarTrashRow(store: store, libraryId: libraryId, isSelected: isSelected, onDropIds: onDropIds)
    }

    @ViewBuilder
    private var children: some View {
        let drawn = Self.shown(store.entries)
        ForEach(drawn.entries) { entry in
            SidebarTrashChildRow(entry: entry, onOpen: onOpen) {
                Task { await store.putBack([entry.id]) }
            }
        }
        if drawn.hidden > 0 {
            Text("\(drawn.hidden) more in the Trash")
                .font(.caption)
                .foregroundStyle(.secondary)
                .listRowInsets(SidebarRowMetrics.insets(.libraryItem))
                .contentShape(Rectangle())
                .onTapGesture(perform: onOpen)
        }
    }
}

/// One thing in the Trash, under the Trash row: its name, and Put Back on the menu. A click opens the Trash pane. The
/// List indents it under the Trash row, as it indents a folder's children.
struct SidebarTrashChildRow: View {
    let entry: TrashEntry
    let onOpen: () -> Void
    let onPutBack: () -> Void

    var body: some View {
        SidebarNodeLabel(name: entry.name, systemImage: entry.isFolder ? "folder" : "doc")
            .listRowInsets(SidebarRowMetrics.insets(.libraryItem))
            .contentShape(Rectangle())
            .onTapGesture(perform: onOpen)
            .contextMenu {
                Button("Put Back", action: onPutBack)
            }
            .help(entry.whereAndWhenText)
            .accessibilityElement(children: .combine)
            .accessibilityLabel(entry.name)
            .accessibilityHint("In the Trash. \(entry.whereAndWhenText)")
    }
}

#Preview("Trash folder: open, with a long tail") {
    let library = LibraryPreviewFixtures.library
    let entries = (0..<3).map {
        TrashEntry(id: "d\($0)", name: "Letters \($0)", isFolder: $0 == 0, fromWhere: "Box 3", why: "Deleted by ana")
    }
    return List {
        SidebarTrashNode(store: TrashStore(client: library.ficheroClient, entries: entries), libraryId: library.id)
        SidebarTrashChildRow(entry: entries[1], onOpen: {}, onPutBack: {})
    }
    .listStyle(.sidebar)
    .frame(width: 260, height: 220)
}
