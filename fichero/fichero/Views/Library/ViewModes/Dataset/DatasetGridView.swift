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
            // ponytail: no column sorting yet — server-side sort exists in
            // DatasetRequest; wire header sorting when someone needs it.
            Table(store.page?.rows ?? [], selection: $selection) {
                TableColumn("Name") { row in
                    Text(row.name)
                        .lineLimit(1)
                }
                TableColumnForEach(store.declaredAttributes, id: \.self) { attr in
                    TableColumn(attr) { row in
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

    private func row(_ id: DatasetPage.Row.ID) -> DatasetPage.Row? {
        store.page?.rows.first { $0.id == id }
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
