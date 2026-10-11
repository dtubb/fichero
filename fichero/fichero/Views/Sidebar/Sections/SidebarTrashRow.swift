import SwiftUI

/// The nodes every project's section draws after its items, in order (ruled 2026-10-10): its knowledge rows,
/// Models, and Trash last. `unifiedLibrarySections` draws them from this list for each project and for the
/// always-there project's top section alike, so the order is one declaration.
enum SidebarProjectNode: CaseIterable, Hashable {
    case knowledge, models, trash

    nonisolated static let order: [SidebarProjectNode] = [.knowledge, .models, .trash]
}

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
    var isSelected = false

    var body: some View {
        // A plain row, no chevron (Daniel, 2026-10-11), drawn as a top-level file row is: the outline keeps the
        // chevrons' strip for every row at a level, so the name lines up with Sources and Workflows when it sits
        // beside a 16-point icon at the folder rows' spacing (`SidebarNodeLabel`). The Label it was had a wider
        // icon slot, which pushed its name right.
        SidebarNodeLabel(name: Self.name, systemImage: Self.systemImage(isEmpty: store.isEmpty))
            .sidebarDropHighlight(false, selected: isSelected)
            .tag(SidebarDestination.trash(libraryId: libraryId))
        .listRowInsets(SidebarRowMetrics.insets(.libraryItem))
        .accessibilityElement(children: .combine)
        .accessibilityLabel(Self.name)
        .accessibilityValue(store.isEmpty ? "Empty" : "\(store.entries.count) items")
    }
}

/// A project node's icon and name, composed as the item rows compose theirs (`SidebarItemRow.itemLabel`: an
/// `HStack` at spacing 6, the icon 16 points wide), so a node row's name lines up with the folders' names.
struct SidebarNodeLabel: View {
    /// The spacing and icon width `SidebarItemRow.itemLabel` and `SidebarRowLabelCore` use.
    nonisolated static let spacing: CGFloat = 6
    nonisolated static let iconWidth: CGFloat = 16

    let name: String
    let systemImage: String

    var body: some View {
        HStack(spacing: Self.spacing) {
            Image(systemName: systemImage)
                .frame(width: Self.iconWidth, alignment: .center)
            Text(name)
                .lineLimit(1)
                .truncationMode(.middle)
        }
        .padding(.vertical, 1)
        .frame(maxWidth: .infinity, alignment: .leading)
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
