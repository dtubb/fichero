import SwiftUI

// MARK: - Timeline renderer (datasets Stage 2)

/// Rows grouped by the date role's month, oldest first — a reading timeline,
/// with per-month counts from the engine's bins where present.
struct DatasetTimelineView: View {
    let store: DatasetModeStore
    var onOpen: (DatasetPage.Row) -> Void = { _ in }

    var body: some View {
        if store.attributeForRole["date"] == nil {
            DatasetMissingRoleView(role: "date", renderer: "timeline")
        } else {
            List {
                ForEach(store.rowsByMonth(), id: \.month) { group in
                    Section {
                        ForEach(group.rows) { row in
                            timelineRow(row)
                                .contentShape(Rectangle())
                                .onTapGesture(count: 2) { onOpen(row) }
                                // Touch parity: iPad has no double-click.
                                .contextMenu { Button("Open") { onOpen(row) } }
                        }
                    } header: {
                        Text(monthLabel(group.month))
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .listStyle(.inset)
        }
    }

    private func timelineRow(_ row: DatasetPage.Row) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            if let dateAttr = store.attributeForRole["date"],
               let date = store.text(dateAttr, of: row) {
                Text(date)
                    .font(.caption)
                    .monospacedDigit()
                    .foregroundStyle(.secondary)
                    .frame(width: 84, alignment: .leading)
            }
            Text(row.name)
                .lineLimit(1)
            if let subtitleAttr = store.attributeForRole["subtitle"],
               let subtitle = store.text(subtitleAttr, of: row) {
                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Spacer(minLength: 0)
        }
    }

    private func monthLabel(_ month: String?) -> String {
        guard let month else { return "Undated" }
        let pieces = month.split(separator: "-")
        guard pieces.count == 2, let monthNumber = Int(pieces[1]),
              (1...12).contains(monthNumber) else { return month }
        return "\(Calendar.current.monthSymbols[monthNumber - 1]) \(pieces[0])"
    }
}
