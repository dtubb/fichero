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
    /// Nil = the Text column is read-only; set, its cells commit through
    /// updateDocument(pageContent:), which stamps the user-edit marker.
    var documentService: DocumentService?
    /// Shared with the shell (2026-08-16): sheet row selection routes
    /// preview/reader/inspector, same as every other data renderer. A Set
    /// binding also gives the Table native ⌘/⇧ multi-select.
    @Binding var selection: Set<String>
    var onOpen: (DatasetPage.Row) -> Void = { _ in }
    var onOpenSource: (DatasetPage.Row) -> Void = { _ in }
    @State private var sortOrder: [DatasetAttributeComparator] = []
    /// Per-window column layout (visibility + order), persisted — the
    /// metadata affordance for the sheet.
    @SceneStorage("datasetSheetColumns")
    private var columnCustomization: TableColumnCustomization<DatasetPage.Row>

    var body: some View {
        if store.declaredAttributes.isEmpty && !store.hasDateSource {
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
            // Column DEFAULTS are the sheet's reading order (Daniel
            // 2026-08-16/17: "hide the name have date first and text
            // second"): Date leads, Text follows, Name ships HIDDEN — an
            // entry's name IS its date, so the column is duplication.
            // `columnCustomization` makes every column native: show/hide
            // from the header context menu, reorder by dragging headers.
            Table(sortedRows, selection: $selection, sortOrder: $sortOrder,
                  columnCustomization: $columnCustomization) {
                // The document's OWN extracted date — only when no date
                // attribute column will already carry it.
                if store.hasDateSource && store.attributeForRole["date"] == nil {
                    TableColumn("Date", sortUsing: DatasetAttributeComparator(key: .date)) { row in
                        Text(row.dateOriginal ?? row.dateIso ?? "")
                            .lineLimit(1)
                            .foregroundStyle(.secondary)
                    }
                    .customizationID("date")
                }
                // The entry's transcript, first-class (Daniel 2026-08-14
                // night: "just dates, no transcript"). Full Text mode lifts
                // the line cap so whole entries read in place ("can't we
                // have multiple lines of text on one").
                TableColumn("Text", sortUsing: DatasetAttributeComparator(key: .text)) { row in
                    if let documentService {
                        // Edits commit on submit/focus-out and persist with
                        // the user-edited stamp — machine reruns can never
                        // clobber a sheet correction (Daniel 2026-08-16:
                        // "we can edit dates, but not text").
                        // ponytail: single-line field over the excerpt; a
                        // long-form editor lives in the reader.
                        DatasetGridCell(
                            text: store.displayExcerpt(of: row) ?? ""
                        ) { newValue in
                            Task { await store.saveText(newValue, on: row, service: documentService) }
                        }
                    } else {
                        Text(store.displayExcerpt(of: row) ?? "")
                            .lineLimit(store.textDetail == .full ? nil : 1)
                            .foregroundStyle(.secondary)
                            .help(store.displayExcerpt(of: row) ?? "")
                    }
                }
                .customizationID("text")
                TableColumn("Name", sortUsing: DatasetAttributeComparator(attr: nil)) { row in
                    Text(row.name)
                        .lineLimit(1)
                }
                .customizationID("name")
                .defaultVisibility(.hidden)
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
                    .customizationID(attr)
                }
            }
            .contextMenu(forSelectionType: DatasetPage.Row.ID.self) { ids in
                Button("Open") {
                    if let id = ids.first, let row = row(id) { onOpen(row) }
                }
                Button("Show Source Page") {
                    if let id = ids.first, let row = row(id), row.parentId != nil {
                        onOpenSource(row)
                    }
                }
            } primaryAction: { ids in
                if let id = ids.first, let row = row(id) { onOpen(row) }
            }
        }
    }

    private var sortedRows: [DatasetPage.Row] {
        // Chronological until the user sorts a column — the same default
        // feed as cards (2026-08-15 night: "its not in order though").
        let rows = store.orderedVisibleRows
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
    /// What the column sorts by (#4595 — Date and Text headers must sort
    /// like every other Mac table's).
    enum Key: Hashable {
        case name
        case date
        case text
        case attribute(String)
    }

    var key: Key
    var order: SortOrder = .forward

    init(key: Key, order: SortOrder = .forward) {
        self.key = key
        self.order = order
    }

    /// Legacy spelling used by the attribute columns: nil = name.
    init(attr: String?, order: SortOrder = .forward) {
        self.key = attr.map { .attribute($0) } ?? .name
        self.order = order
    }

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
        switch key {
        case .name:
            return row.name
        case .date:
            // ISO sorts lexically == chronologically; raw original as backup.
            return row.dateIso ?? row.dateOriginal
        case .text:
            return row.excerpt
        case .attribute(let attr):
            guard let value = row.attributes[attr], let value else { return nil }
            return String(describing: value)
        }
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
    DatasetGridView(store: .previewDiary(), selection: .constant([]))
        .frame(width: 860, height: 600)
}
