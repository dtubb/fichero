import SwiftUI

/// A project's Trash row (#2077, #5243, `safety.trash.a-place-in-the-sidebar`; ruled 2026-10-10):
/// the last row of each project's section, the always-there project's included (its row ends the
/// top section). Always drawn, since the Trash is a place a person goes to, and its icon shows
/// whether that Trash holds anything. Tagged with its `SidebarDestination`, so the list's own
/// selection routes it and the Library pane lists that project's Trash.
struct SidebarTrashRow: View {
    /// The row's name in the sidebar and to VoiceOver.
    nonisolated static let name = "Trash"

    /// The icon: an empty bin, or a full one while the Trash holds anything.
    nonisolated static func systemImage(isEmpty: Bool) -> String {
        isEmpty ? "trash" : "trash.fill"
    }

    let store: TrashStore
    let libraryId: UUID

    var body: some View {
        Label(Self.name, systemImage: Self.systemImage(isEmpty: store.isEmpty))
            .tag(SidebarDestination.trash(libraryId: libraryId))
            .listRowInsets(SidebarRowMetrics.insets(.libraryItem))
            .accessibilityValue(store.isEmpty ? "Empty" : "\(store.entries.count) items")
    }
}

#Preview("Trash rows: empty and holding items") {
    let library = LibraryPreviewFixtures.library
    let full = TrashStore(
        client: library.ficheroClient,
        entries: [TrashEntry(id: "a", name: "Letters", fromWhere: "Box 3", why: "Deleted by ana")]
    )
    return List {
        SidebarTrashRow(store: TrashStore(client: library.ficheroClient), libraryId: library.id)
        SidebarTrashRow(store: full, libraryId: UUID())
    }
    .listStyle(.sidebar)
    .frame(width: 260, height: 120)
}
