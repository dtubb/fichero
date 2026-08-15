import SwiftUI

// MARK: - Grid renderer (datasets Stage 2 — the spreadsheet)

/// "Grid is more like spreadsheet" (Daniel 2026-08-14): rows are nodes,
/// columns are the declared attributes, and cells edit in place — each
/// commit persists through the engine first, then the store replaces just
/// that row (no wholesale re-render).
struct DatasetGridView: View {
    let store: DatasetModeStore
    /// Nil = read-only cells (previews, closed library).
    var entityService: EntityService?
    var onOpen: (DatasetPage.Row) -> Void = { _ in }

    @State private var selection: DatasetPage.Row.ID?
    @State private var sortOrder: [DatasetAttributeComparator] = []

    var body: some View {
        if store.declaredAttributes.isEmpty {
            ContentUnavailableView(
                "No Attributes Declared",
                systemImage: "tablecells",
                description: Text(
                    "The grid's columns come from the document type's declared "
                        + "attributes. Add some in the type editor "
                        + "(Inspector → Info → Prototype → Edit Types…)."
                )
            )
        } else {
            // ponytail: header sort is LOCAL over the loaded page (≤500
            // rows, instant). Server-side sort (DatasetRequest.sortAttr)
            // takes over when paging beyond one page arrives.
            Table(sortedRows, selection: $selection, sortOrder: $sortOrder) {
                TableColumn("Name", sortUsing: DatasetAttributeComparator(attr: nil)) { row in
                    Text(row.name)
                        .lineLimit(1)
                }
                // The entry's transcript, first-class beside the name
                // (Daniel 2026-08-14 night: "just dates, no transcript").
                TableColumn("Text") { row in
                    Text(row.excerpt ?? "")
                        .lineLimit(1)
                        .foregroundStyle(.secondary)
                        .help(row.excerpt ?? "")
                }
                TableColumnForEach(store.declaredAttributes, id: \.self) { attr in
                    TableColumn(attr, sortUsing: DatasetAttributeComparator(attr: attr)) { row in
                        if let entityService {
                            DatasetGridCell(
                                text: store.text(attr, of: row) ?? ""
                            ) { newValue in
                                Task {
                                    await store.saveAttribute(
                                        attr,
                                        value: newValue.isEmpty ? nil : newValue,
                                        on: row,
                                        entityService: entityService
                                    )
                                }
                            }
                        } else {
                            Text(store.text(attr, of: row) ?? "")
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }
                    }
                }
            }
            .contextMenu(forSelectionType: DatasetPage.Row.ID.self) { ids in
                Button("Open") {
                    if let id = ids.first, let row = row(id) { onOpen(row) }
                }
            } primaryAction: { ids in
                if let id = ids.first, let row = row(id) { onOpen(row) }
            }
        }
    }

    private var sortedRows: [DatasetPage.Row] {
        let rows = store.page?.rows ?? []
        guard !sortOrder.isEmpty else { return rows }
        return rows.sorted { lhs, rhs in
            for comparator in sortOrder {
                switch comparator.compare(lhs, rhs) {
                case .orderedAscending: return true
                case .orderedDescending: return false
                case .orderedSame: continue
                }
            }
            return false
        }
    }

    private func row(_ id: DatasetPage.Row.ID) -> DatasetPage.Row? {
        store.page?.rows.first { $0.id == id }
    }
}

/// Sorts grid rows by one attribute's EFFECTIVE own value — numerically when
/// both sides parse as numbers, lexically otherwise; missing values last in
/// either direction. `attr == nil` sorts by the node name.
struct DatasetAttributeComparator: SortComparator, Hashable {
    var attr: String?
    var order: SortOrder = .forward

    func compare(_ lhs: DatasetPage.Row, _ rhs: DatasetPage.Row) -> Foundation.ComparisonResult {
        switch (text(of: lhs), text(of: rhs)) {
        case (nil, nil): return .orderedSame
        // Missing values sort LAST in BOTH directions (direction applies
        // only to real values), so flipping a column never buries the data
        // under the blanks.
        case (nil, _): return .orderedDescending
        case (_, nil): return .orderedAscending
        case (let lhs?, let rhs?):
            let result = valueCompare(lhs, rhs)
            return order == .forward ? result : result.reversed
        }
    }

    private func text(of row: DatasetPage.Row) -> String? {
        guard let attr else { return row.name }
        guard let value = row.attributes[attr], let value else { return nil }
        return String(describing: value)
    }

    private func valueCompare(_ lhs: String, _ rhs: String) -> Foundation.ComparisonResult {
        if let leftNumber = Double(lhs), let rightNumber = Double(rhs) {
            if leftNumber == rightNumber { return .orderedSame }
            return leftNumber < rightNumber ? .orderedAscending : .orderedDescending
        }
        return lhs.localizedStandardCompare(rhs)
    }
}

private extension Foundation.ComparisonResult {
    var reversed: Foundation.ComparisonResult {
        switch self {
        case .orderedAscending: .orderedDescending
        case .orderedDescending: .orderedAscending
        case .orderedSame: .orderedSame
        }
    }
}

/// One editable cell: a TextField over a local draft that only commits on
/// submit/focus-out, so keystrokes never round-trip the engine.
private struct DatasetGridCell: View {
    let text: String
    let onCommit: (String) -> Void

    @State private var draft: String = ""
    @FocusState private var isFocused: Bool

    var body: some View {
        TextField("", text: $draft)
            .textFieldStyle(.plain)
            .lineLimit(1)
            .focused($isFocused)
            .onAppear { draft = text }
            .onChange(of: text) { _, newValue in
                if !isFocused { draft = newValue }
            }
            .onSubmit { commit() }
            .onChange(of: isFocused) { _, focused in
                if !focused { commit() }
            }
    }

    private func commit() {
        let value = draft.trimmingCharacters(in: .whitespaces)
        guard value != text else { return }
        onCommit(value)
    }
}

#Preview("Grid — diary") {
    DatasetGridView(store: .previewDiary())
        .frame(width: 860, height: 600)
}
