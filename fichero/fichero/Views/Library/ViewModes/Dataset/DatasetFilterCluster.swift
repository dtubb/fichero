import SwiftUI

// MARK: - The dataset facets, in the ONE bottom bar (Daniel, 2026-08-24)
//
// Consolidated 2026-08-27 (Daniel: "can't we consolidate some of these
// library buttons… they are split apart and forced to become a lozenge when
// too narrow"): SEVEN separate controls became TWO here plus the shared
// metadata popover —
//   · Show   = Spreads/Pages levels AND the document types, one menu ("pages
//              and spreads is really the same as all types").
//   · Filter = dated/undated plus the count + Clear ("dated and undated can
//              be combined… maybe some can be in the filter menu").
//   · The excerpt/full-text choice moved into the Metadata popover
//              ("the full text excerpt is more logically part of the
//              metadata") — see LibraryRowAttributesButton.

/// Inline face: the Show + Filter menus.
struct DatasetFilterCluster: View {
    let store: DatasetModeStore
    let documentStore: DocumentStore

    var body: some View {
        datasetShowMenu(store, documentStore)
            .labelStyle(.iconOnly)
            .foregroundStyle(store.prototypeFilter == nil ? AnyShapeStyle(.secondary) : AnyShapeStyle(Color.accentColor))
        datasetFilterMenu(store)
            .labelStyle(.iconOnly)
            .foregroundStyle(store.dateFilter == .all ? AnyShapeStyle(.secondary) : AnyShapeStyle(Color.accentColor))
    }
}

/// Overflow face: the same facets as titled submenus, for narrow widths.
struct DatasetFilterClusterMenu: View {
    let store: DatasetModeStore
    let documentStore: DocumentStore

    var body: some View {
        datasetShowMenu(store, documentStore)
        datasetFilterMenu(store)
    }
}

/// One "what am I looking at" menu: the reading level (spreads ↔ pages) and
/// the document types are the same question at two grains, so they share it.
@MainActor
private func datasetShowMenu(_ store: DatasetModeStore, _ documentStore: DocumentStore) -> some View {
    Menu {
        Section("Level") {
            ForEach(LibraryLevel.allCases) { level in
                Button {
                    Task { await documentStore.setLibraryLevel(level) }
                } label: {
                    Label(level.title, systemImage: level.systemImage)
                    if documentStore.libraryLevel == level {
                        Image(systemName: "checkmark")
                    }
                }
            }
        }
        if store.availablePrototypes.count > 1 {
            Section("Type") {
                Button {
                    store.prototypeFilter = nil
                } label: {
                    Text("All Types")
                    if store.prototypeFilter == nil {
                        Image(systemName: "checkmark")
                    }
                }
                ForEach(store.availablePrototypes, id: \.self) { key in
                    Button {
                        store.prototypeFilter = key
                    } label: {
                        Text(key.replacingOccurrences(of: "_", with: " ").capitalized)
                        if store.prototypeFilter == key {
                            Image(systemName: "checkmark")
                        }
                    }
                }
            }
        }
    } label: {
        Label("Show", systemImage: "square.grid.2x2")
    }
    .menuStyle(.borderlessButton)
    .fixedSize()
    .help("Choose the reading level (spreads or pages) and which document types to show")
}

/// Dates + the active-filter readout + Clear, one menu.
@MainActor
private func datasetFilterMenu(_ store: DatasetModeStore) -> some View {
    Menu {
        Section("Dates") {
            ForEach(DatasetDateFilter.allCases) { choice in
                Button {
                    store.dateFilter = choice
                } label: {
                    Text(choice.rawValue)
                    if store.dateFilter == choice {
                        Image(systemName: "checkmark")
                    }
                }
            }
        }
        if store.dateFilter != .all || store.prototypeFilter != nil {
            Divider()
            Text("Showing \(store.visibleRows.count) of \(store.page?.rows.count ?? 0)")
            Button("Clear Filters") {
                store.dateFilter = .all
                store.prototypeFilter = nil
            }
        }
    } label: {
        Label("Filter", systemImage: "line.3.horizontal.decrease.circle")
    }
    .menuStyle(.borderlessButton)
    .fixedSize()
    .help("Show all, dated, or undated rows; clear active dataset filters")
}
