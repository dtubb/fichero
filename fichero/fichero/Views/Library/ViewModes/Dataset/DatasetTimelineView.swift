import SwiftUI

// MARK: - Timeline renderer (datasets Stage 2)

/// Rows grouped by the date role's month, oldest first — a reading timeline,
/// with per-month counts from the engine's bins where present.
struct DatasetTimelineView: View {
    let store: DatasetModeStore
    var onOpen: (DatasetPage.Row) -> Void = { _ in }

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
                                    .onTapGesture(count: 2) { onOpen(row) }
                                    // Touch parity: iPad has no double-click.
                                    .contextMenu { Button("Open") { onOpen(row) } }
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
            if let excerpt = row.excerpt {
                Text(excerpt)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
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
}

#Preview("Timeline — diary") {
    DatasetTimelineView(store: .previewDiary())
        .frame(width: 640, height: 640)
}
