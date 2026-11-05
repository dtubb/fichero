import SwiftUI

/// The Trash as a plain folder in the tree (`safety.trash.is-a-folder-in-the-sidebar`, owner design 2026-11-05): the Trash row
/// with a chevron that opens what is in it as rows beneath, each with Put Back on its menu. The row itself still opens the
/// Trash pane (`SidebarDestination.trash`), where Put Back and Empty Trash work on a selection.
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

    var body: some View {
        SidebarTrashRow(
            store: store, libraryId: libraryId, isSelected: isSelected, onDropIds: onDropIds,
            isExpanded: store.isEmpty ? nil : $isExpanded
        )
        if isExpanded && !store.isEmpty {
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
                    .padding(.leading, SidebarTrashChildRow.indent)
                    .listRowInsets(SidebarRowMetrics.insets(.libraryItem))
                    .contentShape(Rectangle())
                    .onTapGesture(perform: onOpen)
            }
        }
    }
}

/// One thing in the Trash, under the Trash row: its name, and Put Back on the menu. A click opens the Trash pane.
struct SidebarTrashChildRow: View {
    /// How far a child sits in from the Trash row's name.
    nonisolated static let indent: CGFloat = 18

    let entry: TrashEntry
    let onOpen: () -> Void
    let onPutBack: () -> Void

    var body: some View {
        SidebarNodeLabel(name: entry.name, systemImage: entry.isFolder ? "folder" : "doc")
            .padding(.leading, Self.indent)
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
