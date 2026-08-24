import SwiftUI

// MARK: - The dataset facets, in the ONE bottom bar (Daniel, 2026-08-24)
//
// The dataset renderers used to draw their own PaneFilterBar above the
// library's action bar — two stacked bars, the exact defect the one-bottom-
// toolbar ruling names. The three facet menus (lifted verbatim from the old
// datasetFilterBar) now render as this cluster inside libraryMiniToolbar,
// icon-only like sort/filter beside them, with the accent tint carrying the
// "a facet is active" signal the text labels used to.

/// Inline face: icon-only menus + the filtered count/Clear pair.
struct DatasetFilterCluster: View {
    let store: DatasetModeStore

    var body: some View {
        datasetDateMenu(store)
            .labelStyle(.iconOnly)
            .foregroundStyle(store.dateFilter == .all ? AnyShapeStyle(.secondary) : AnyShapeStyle(Color.accentColor))
        datasetTextMenu(store)
            .labelStyle(.iconOnly)
        if store.availablePrototypes.count > 1 {
            datasetTypeMenu(store)
                .labelStyle(.iconOnly)
                .foregroundStyle(store.prototypeFilter == nil ? AnyShapeStyle(.secondary) : AnyShapeStyle(Color.accentColor))
        }
        if store.dateFilter != .all || store.prototypeFilter != nil {
            Text("\(store.visibleRows.count) of \(store.page?.rows.count ?? 0)")
                .font(.caption)
                .foregroundStyle(.secondary)
                .monospacedDigit()
            Button("Clear") {
                store.dateFilter = .all
                store.prototypeFilter = nil
            }
            .buttonStyle(.borderless)
            .help("Clear dataset filters")
        }
    }
}

/// Overflow face: the same facets as titled submenus, for narrow widths.
struct DatasetFilterClusterMenu: View {
    let store: DatasetModeStore

    var body: some View {
        datasetDateMenu(store)
        datasetTextMenu(store)
        if store.availablePrototypes.count > 1 {
            datasetTypeMenu(store)
        }
        Button("Clear Dataset Filters") {
            store.dateFilter = .all
            store.prototypeFilter = nil
        }
        .disabled(store.dateFilter == .all && store.prototypeFilter == nil)
    }
}

// The menu bodies, ONE definition for both faces (lifted verbatim from the
// deleted datasetFilterBar — iterate, never replace).

@MainActor
private func datasetDateMenu(_ store: DatasetModeStore) -> some View {
    Menu {
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
    } label: {
        Label(
            store.dateFilter == .all ? "Dates" : store.dateFilter.rawValue,
            systemImage: "calendar.badge.checkmark"
        )
    }
    .menuStyle(.borderlessButton)
    .fixedSize()
    .help("Show all rows, only dated rows, or only undated rows")
}

@MainActor
private func datasetTextMenu(_ store: DatasetModeStore) -> some View {
    Menu {
        ForEach(DatasetModeStore.TextDetail.allCases) { choice in
            Button {
                store.textDetail = choice
            } label: {
                Text(choice.rawValue)
                if store.textDetail == choice {
                    Image(systemName: "checkmark")
                }
            }
        }
    } label: {
        Label("Text", systemImage: "text.alignleft")
    }
    .menuStyle(.borderlessButton)
    .fixedSize()
    .help("Show the excerpt or the full entry text on cards")
}

@MainActor
private func datasetTypeMenu(_ store: DatasetModeStore) -> some View {
    Menu {
        Button {
            store.prototypeFilter = nil
        } label: {
            Text("All Types")
            if store.prototypeFilter == nil {
                Image(systemName: "checkmark")
            }
        }
        Divider()
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
        Label("Type", systemImage: "tag")
    }
    .menuStyle(.borderlessButton)
    .fixedSize()
    .help("Show only rows of one document type")
}
