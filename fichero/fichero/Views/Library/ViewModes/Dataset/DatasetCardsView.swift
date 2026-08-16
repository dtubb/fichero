import SwiftUI

// MARK: - Cards renderer (datasets Stage 2)

/// A grid of cards: title role (or node name) as headline, subtitle role as
/// caption, then every declared attribute with a value as a labeled line.
///
/// Cards are chronological (date then name, undated last), selectable
/// (click selects and routes the three panes; ⌘-click toggles a batch), and
/// actionable in place: Edit Date…, and Run Workflow over the selection —
/// which is how "select entries, run SVO on them" works (Daniel 2026-08-15
/// night).
struct DatasetCardsView: View {
    let store: DatasetModeStore
    var entityService: EntityService?
    @Binding var selection: Set<String>
    var workflows: [WorkflowSidebarItem] = []
    var onOpen: (DatasetPage.Row) -> Void = { _ in }
    var onOpenSource: (DatasetPage.Row) -> Void = { _ in }
    var onRunWorkflow: (String, [String], String?, String?) -> Void = { _, _, _, _ in }

    @State private var dateEditRow: DatasetPage.Row?
    @State private var dateDraft = ""
    /// ⇧-click range anchor — SelectionGrammar owns the semantics (#4436).
    @State private var selectionAnchor: String?

    private let columns = [GridItem(.adaptive(minimum: 220, maximum: 320), spacing: 12)]

    var body: some View {
        ScrollView {
            LazyVGrid(columns: columns, spacing: 12) {
                ForEach(store.orderedVisibleRows) { row in
                    card(row)
                        .onTapGesture { handleTap(row) }
                        .contextMenu { cardMenu(row) }
                }
            }
            .padding(12)
        }
        .alert(
            "Edit Date",
            isPresented: Binding(
                get: { dateEditRow != nil },
                set: { if !$0 { dateEditRow = nil } }
            )
        ) {
            TextField("YYYY-MM-DD", text: $dateDraft)
            Button("Save") { commitDateEdit() }
            Button("Cancel", role: .cancel) { dateEditRow = nil }
        } message: {
            Text("The entry moves to its new day everywhere — timeline, calendar and cards.")
        }
    }

    /// Plain click selects (and routes preview/reader to the row); ⌘-click
    /// toggles, ⇧-click extends a chronological range — the ONE click
    /// grammar, through SelectionGrammar (#4436), never hand-rolled.
    private func handleTap(_ row: DatasetPage.Row) {
        var modifiers: SelectionGrammar.Modifiers = []
        #if os(macOS)
        if NSEvent.modifierFlags.contains(.command) { modifiers.insert(.command) }
        if NSEvent.modifierFlags.contains(.shift) { modifiers.insert(.shift) }
        #endif
        let result = SelectionGrammar.click(
            id: row.id,
            in: store.orderedVisibleRows.map(\.id),
            selection: selection,
            anchor: selectionAnchor,
            modifiers: modifiers
        )
        selection = result.selection
        selectionAnchor = result.anchor
        if modifiers.isEmpty {
            onOpen(row)
        }
    }

    /// The Finder rule, as everywhere else: the batch applies only when it
    /// INCLUDES the clicked card; right-clicking outside it acts on the
    /// clicked card alone.
    private func workflowTargets(for row: DatasetPage.Row) -> [String] {
        selection.contains(row.id) ? Array(selection) : [row.id]
    }

    @ViewBuilder
    private func cardMenu(_ row: DatasetPage.Row) -> some View {
        Button("Open") { onOpen(row) }
        if row.parentId != nil {
            Button("Show Source Page") { onOpenSource(row) }
        }
        if store.attributeForRole["date"] != nil, entityService != nil {
            Button("Edit Date…") {
                dateDraft = store.dateValue(of: row) ?? ""
                dateEditRow = row
            }
        }
        if !workflows.isEmpty {
            Divider()
            let targets = workflowTargets(for: row)
            Menu("Run Workflow") {
                if targets.count > 1 {
                    // Scope stated BEFORE the click, same as the sidebar and
                    // library menus (2026-08-15).
                    Text("Runs on \(targets.count) entries")
                    Divider()
                }
                RunWorkflowSubmenuItems(workflows: workflows) { workflowId, provider, model in
                    onRunWorkflow(workflowId, targets, provider, model)
                }
            }
        }
    }

    private func commitDateEdit() {
        guard let row = dateEditRow,
              let dateAttr = store.attributeForRole["date"],
              let entityService else { return }
        let value = dateDraft.trimmingCharacters(in: .whitespaces)
        dateEditRow = nil
        Task { @MainActor in
            await store.saveAttribute(
                dateAttr, value: value.isEmpty ? nil : value,
                on: row, entityService: entityService
            )
        }
    }

    private func card(_ row: DatasetPage.Row) -> some View {
        let isSelected = selection.contains(row.id)
        return VStack(alignment: .leading, spacing: 6) {
            Text(titleText(row))
                .font(.headline)
                .lineLimit(2)
            // The date role is a diary entry's identity — a formatted line
            // right under the headline, not a raw attribute row. Skipped
            // when the headline IS the date (a "1942-02-03"-named entry
            // with no title role would read the same date twice).
            if let rawDate = store.dateValue(of: row),
               dateLine(rawDate) != titleText(row) {
                Text(dateLine(rawDate))
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            if let subtitleAttr = store.attributeForRole["subtitle"],
               let subtitle = store.text(subtitleAttr, of: row) {
                Text(subtitle)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
            // The entry's own words — the reason the card exists (Daniel
            // 2026-08-14 night: "just dates, no transcript"). A leading
            // date-heading line is dropped at display time (the date is
            // the headline already); Full Text lifts the line cap.
            if let excerpt = store.displayExcerpt(of: row) {
                Text(excerpt)
                    .font(.callout)
                    .lineLimit(store.textDetail == .full ? nil : 4)
                    .foregroundStyle(.primary.opacity(0.85))
                    .padding(.top, 2)
            }
            attributeLines(row)
            Spacer(minLength: 0)
            // The REFERENCE, visible and one click away (Daniel 2026-08-15):
            // every extracted card points back at the page it came from.
            if row.parentId != nil {
                Button {
                    onOpenSource(row)
                } label: {
                    Label("Source page", systemImage: "photo")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
                .help("Open the page this entry came from")
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, minHeight: 110, alignment: .topLeading)
        .background(.quaternary.opacity(0.4), in: RoundedRectangle(cornerRadius: 8))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(isSelected ? Color.accentColor : .clear, lineWidth: 2)
        )
        .contentShape(Rectangle())
    }

    /// The title role names the card; the node NAME is the fallback — shown
    /// as the FORMATTED date when the name is itself a bare date (the diary
    /// workflow names entries by their date).
    private func titleText(_ row: DatasetPage.Row) -> String {
        guard let titleAttr = store.attributeForRole["title"],
              let title = store.text(titleAttr, of: row) else {
            return DatasetModeStore.longDate(row.name) ?? row.name
        }
        return title
    }

    private func dateLine(_ raw: String) -> String {
        DatasetModeStore.longDate(raw) ?? raw
    }

    @ViewBuilder
    private func attributeLines(_ row: DatasetPage.Row) -> some View {
        // Role-bound attributes render through their surfaces (headline,
        // date line, the map) — repeating them as raw caption rows is noise
        // (the geo "5.69,-76.66" line, preview review 2026-08-15).
        let roleBound = Set(store.attributeForRole.values)
        let names = store.declaredAttributes
            .filter { !roleBound.contains($0) }
            .prefix(5)
        ForEach(Array(names), id: \.self) { name in
            if let value = store.text(name, of: row) {
                HStack(alignment: .firstTextBaseline, spacing: 4) {
                    Text(name)
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                    Text(value)
                        .font(.caption)
                        .lineLimit(1)
                }
            }
        }
    }
}

#Preview("Cards — diary") {
    DatasetCardsView(store: .previewDiary(), selection: .constant(["jan4-second"]))
        .frame(width: 780, height: 640)
}
