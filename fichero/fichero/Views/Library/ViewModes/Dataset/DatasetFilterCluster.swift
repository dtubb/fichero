import SwiftUI

// MARK: - The dataset facets, in the ONE bottom bar (Daniel, 2026-08-24)
//
// Consolidated 2026-08-27 (Daniel: "can't we consolidate some of these
// library buttons… they are split apart and forced to become a lozenge when
// too narrow"): SEVEN separate controls became TWO here plus the shared
// metadata popover —
//   · Types  = which document types to list. It ALSO carried the Spreads /
//              Pages level until 2026-09-01, when that half went back to the
//              shared Show control every view mode carries — see
//              `datasetShowMenu` for why a mode-local copy made the bar read
//              as a different bar.
//   · Filter = dated/undated plus the count + Clear ("dated and undated can
//              be combined… maybe some can be in the filter menu").
//   · The excerpt/full-text choice moved into the Metadata popover
//              ("the full text excerpt is more logically part of the
//              metadata") — see LibraryRowAttributesButton.

/// Inline face: the Types + Filter menus — EXTRAS added inline to the one
/// library bottom bar, never a replacement for any of its controls.
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

/// Overflow face: the same two extras as titled submenus, for narrow widths.
struct DatasetFilterClusterMenu: View {
    let store: DatasetModeStore
    let documentStore: DocumentStore

    var body: some View {
        datasetShowMenu(store, documentStore)
        datasetFilterMenu(store)
    }
}

/// The document TYPES this dataset holds — the one facet that is genuinely
/// extra to Data mode.
///
/// It used to be a menu called "Show" that also carried the reading level, and
/// the shared Show control was hidden whenever it appeared (Daniel, 2026-08-27:
/// "pages and spreads is really the same as all types"). That reading is true
/// of the QUESTION and false of the CONTROL: the reading level is a property of
/// the library — `DocumentStore.libraryLevel`, which the engine resolves and
/// every other mode reads through the shared Show menu — so putting it in a
/// mode-local menu meant Data mode replaced a bar control with a differently
/// named one in the same slot. That is what "data/dataset mode shows a
/// different bar" was seeing (Daniel, 2026-09-01).
///
/// So: the level went back to the one Show control that every mode carries, and
/// what is left here is only what no other mode has to ask — which types of row
/// to list. Named "Types", because it is now only types.
///
/// `documentStore` is still taken (unused by the menu body) so the two faces
/// keep one call signature and the cluster's callers do not have to know which
/// face needs what.
@MainActor
private func datasetShowMenu(_ store: DatasetModeStore, _ documentStore: DocumentStore) -> some View {
    Menu {
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
    } label: {
        Label("Types", systemImage: "square.grid.2x2")
    }
    .menuStyle(.borderlessButton)
    .fixedSize()
    // Deliberately NOT hidden when the dataset carries a single type: a
    // control that comes and goes with the data is a bar that changes shape
    // under the user, which is the complaint this whole pass is answering.
    .disabled(store.availablePrototypes.isEmpty)
    .help("Choose which document types this dataset lists")
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
