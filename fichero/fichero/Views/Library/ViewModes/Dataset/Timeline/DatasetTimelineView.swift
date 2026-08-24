import SwiftUI

// MARK: - Timeline renderer (datasets Stage 2)

/// Rows grouped by the date role's month, oldest first — a reading timeline,
/// with per-month counts from the engine's bins where present.
struct DatasetTimelineView: View {
    let store: DatasetModeStore
    /// Shared with the shell (2026-08-16): a single click selects and the
    /// shell routes preview/reader/inspector; double-click still opens.
    @Binding var selection: Set<String>
    var onOpen: (DatasetPage.Row) -> Void = { _ in }
    var onOpenSource: (DatasetPage.Row) -> Void = { _ in }
    /// Nil = exclusion items hidden (previews, closed library).
    var documentService: DocumentService?
    var workflows: [WorkflowSidebarItem] = []
    var onRunWorkflow: (String, [String], String?, String?) -> Void = { _, _, _, _ in }

    /// ⇧-click range anchor — SelectionGrammar owns the semantics (#4598,
    /// same pattern as DatasetCardsView; before this a timeline click could
    /// only REPLACE the selection, so multi/discontiguous select was
    /// impossible).
    @State private var selectionAnchor: String?

    var body: some View {
        if !store.hasDateSource {
            DatasetMissingRoleView(role: "date", renderer: "timeline")
        } else {
            // ScrollView, not List: this is a pure reading surface (no
            // selection model), and SwiftUI's NSTableView-backed List
            // asserted inside its outline bookkeeping under the preview
            // host (ViewListTree.visitItem, 2026-08-14). LazyVStack with
            // pinned headers gives the same grouped look without the
            // machinery.
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 0, pinnedViews: .sectionHeaders) {
                    ForEach(store.rowsByMonth(), id: \.month) { group in
                        Section {
                            ForEach(group.rows) { row in
                                timelineRow(row)
                                    .padding(.horizontal, 16)
                                    .padding(.vertical, 5)
                                    .contentShape(Rectangle())
                                    .background(
                                        selection.contains(row.id)
                                            ? Color.accentColor.opacity(0.12) : .clear
                                    )
                                    .onTapGesture(count: 2) { onOpen(row) }
                                    .onTapGesture { handleTap(row) }
                                    // Touch parity: iPad has no double-click.
                                    .contextMenu { rowMenu(row) }
                                Divider().padding(.leading, 16)
                            }
                        } header: {
                            Text(monthLabel(group.month))
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(.secondary)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(.horizontal, 16)
                                .padding(.vertical, 6)
                                .background(.bar)
                        }
                    }
                }
            }
        }
    }

    /// "January 4, 1942 — Istmina": the formatted date leads (a diary
    /// entry's identity), the title role follows, then any subtitle. A row
    /// whose name is NOT its date (an image, a report) keeps its name first.
    private func timelineRow(_ row: DatasetPage.Row) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(primaryText(row))
                    .lineLimit(1)
            if let titleAttr = store.attributeForRole["title"],
               let title = store.text(titleAttr, of: row), title != primaryText(row) {
                Text(title)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
                if let subtitleAttr = store.attributeForRole["subtitle"],
                   let subtitle = store.text(subtitleAttr, of: row) {
                    Text(subtitle)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                Spacer(minLength: 0)
            }
            if let excerpt = store.displayExcerpt(of: row) {
                // Full Text lifts the cap, matching the sheet (#4598 —
                // the toggle previously did nothing here).
                Text(excerpt)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .lineLimit(store.textDetail == .full ? nil : 2)
            }
        }
    }

    /// Click with the full Mac grammar over the timeline's visual order
    /// (months, then rows within each month) — ⇧ ranges, ⌘ toggles.
    private func handleTap(_ row: DatasetPage.Row) {
        var modifiers: SelectionGrammar.Modifiers = []
        #if os(macOS)
        if NSEvent.modifierFlags.contains(.command) { modifiers.insert(.command) }
        if NSEvent.modifierFlags.contains(.shift) { modifiers.insert(.shift) }
        #endif
        let orderedIds = store.rowsByMonth().flatMap { $0.rows.map(\.id) }
        let result = SelectionGrammar.click(
            id: row.id,
            in: orderedIds,
            selection: selection,
            anchor: selectionAnchor,
            modifiers: modifiers
        )
        selection = result.selection
        selectionAnchor = result.anchor
    }

    private func primaryText(_ row: DatasetPage.Row) -> String {
        guard let dateValue = store.dateValue(of: row) else { return row.name }
        // A row NAMED by its date (the diary workflow) reads as the
        // formatted date; a row with its OWN extracted date keeps its name
        // first — "scan_007.png" is still the identity, the date column
        // groups it.
        guard row.name.hasPrefix(dateValue) else { return row.name }
        return DatasetModeStore.longDate(dateValue) ?? row.name
    }

    private func monthLabel(_ month: String) -> String {
        guard month != DatasetModeStore.undatedMonthKey else { return "Undated" }
        let pieces = month.split(separator: "-")
        guard pieces.count == 2, let monthNumber = Int(pieces[1]),
              (1...12).contains(monthNumber) else { return month }
        return "\(Calendar.current.monthSymbols[monthNumber - 1]) \(pieces[0])"
    }

    /// The ONE dataset row menu — Timeline gained exclusion and Run Workflow
    /// by adopting it, rather than being taught them separately.
    private func rowMenu(_ row: DatasetPage.Row) -> some View {
        DatasetRowMenu(
            rows: [row],
            targets: selection.contains(row.id) ? Array(selection) : [row.id],
            documentService: documentService,
            workflows: workflows,
            onOpen: onOpen,
            onOpenSource: onOpenSource,
            onRunWorkflow: onRunWorkflow
        )
    }

}

#Preview("Timeline — diary") {
    DatasetTimelineView(store: .previewDiary(), selection: .constant([]))
        .frame(width: 640, height: 640)

}
