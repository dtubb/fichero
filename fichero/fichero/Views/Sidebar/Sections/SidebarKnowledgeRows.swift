import SwiftUI

/// The sidebar's knowledge rows and the bottom bar's one control that shows or hides them
/// (#5413: `sidebar.knowledge.rows-only-when-non-empty`, `sidebar.knowledge.bottom-bar-toggle`).
@MainActor
enum SidebarKnowledgeRows {
    /// The remembered setting. On (rows shown) until a person turns it off.
    nonisolated static let shownKey = "sidebar.knowledgeRows.shown"

    /// The one declaration of the setting, so the bottom bar, the rows and the tests read and
    /// write the same stored value.
    static func shownSetting(store: UserDefaults? = nil) -> AppStorage<Bool> {
        AppStorage(wrappedValue: true, shownKey, store: store)
    }

    /// The rows a project draws: none while the setting hides them, else its non-empty rows.
    static func rows(of store: KnowledgeRowCountsStore, shown: Bool) -> [KnowledgeCollectionKind] {
        shown ? store.nonEmptyRows : []
    }

    /// The control shows only when at least one open project has a knowledge row to hide.
    static func toggleIsShown(_ stores: [KnowledgeRowCountsStore]) -> Bool {
        stores.contains { !$0.nonEmptyRows.isEmpty }
    }

    static func title(_ kind: KnowledgeCollectionKind) -> String {
        switch kind {
        case .entities: return "Entities"
        case .claims: return "Claims"
        }
    }

    static func systemImage(_ kind: KnowledgeCollectionKind) -> String {
        switch kind {
        case .entities: return "person.2"
        case .claims: return "quote.bubble"
        }
    }
}

/// A project's knowledge rows (Entities, Claims): each drawn only while it holds at least one
/// item, from the project's `KnowledgeRowCountsStore`, and none while the bottom bar's control
/// hides them. Each row is tagged with its `SidebarDestination`, so the list's own selection
/// routes it and opens that project's table (P4, per-library).
struct SidebarKnowledgeRowsNode: View {
    let store: KnowledgeRowCountsStore
    let libraryId: UUID
    var selection: Set<SidebarDestination> = []

    @AppStorage(SidebarKnowledgeRows.shownKey) private var shown = true

    var body: some View {
        ForEach(SidebarKnowledgeRows.rows(of: store, shown: shown), id: \.self) { kind in
            let destination = SidebarDestination.knowledgeCollection(kind, libraryId: libraryId)
            Label(SidebarKnowledgeRows.title(kind), systemImage: SidebarKnowledgeRows.systemImage(kind))
                .sidebarDropHighlight(false, selected: selection.contains(destination))
                .tag(destination)
                .listRowInsets(SidebarRowMetrics.insets(.libraryItem))
        }
    }
}

#Preview("Knowledge rows: entities and claims, citations hidden at 0") {
    let library = LibraryPreviewFixtures.library
    let store = KnowledgeRowCountsStore(
        client: library.ficheroClient,
        counts: [.entities: 12, .claims: 3, .citations: 0]
    )
    return List {
        SidebarKnowledgeRowsNode(store: store, libraryId: library.id)
    }
    .listStyle(.sidebar)
    .frame(width: 260, height: 160)
}
