import SwiftUI

/// Read-only **Cited** ledger: what the conversation actually used, unified
/// across document / research / knowledge provenance (see
/// `docs/design/agentic-surface-consolidation-fabel-review.md`, §3).
///
/// Sits under the pinned-scope editor in the Sources tab, so the tab reads:
/// *pinned = what you gave it · cited = what it used.* Nothing here mutates —
/// it is provenance, surfaced (instrument, not interlocutor).
struct SourcesLedgerView: View {
    let entries: [SourceLedgerEntry]

    private var grouped: [(kind: SourceLedgerEntry.Kind, entries: [SourceLedgerEntry])] {
        [.document, .research, .knowledge].compactMap { kind in
            let matches = entries.filter { $0.kind == kind }
            return matches.isEmpty ? nil : (kind, matches)
        }
    }

    var body: some View {
        if entries.isEmpty {
            EmptyView()
        } else {
            VStack(alignment: .leading, spacing: 8) {
                Text("Cited")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)

                ForEach(grouped, id: \.kind) { group in
                    ForEach(group.entries) { entry in
                        row(entry)
                    }
                }
            }
            .padding(12)
            .accessibilityIdentifier("sourcesLedger")
        }
    }

    @ViewBuilder
    private func row(_ entry: SourceLedgerEntry) -> some View {
        HStack(spacing: 6) {
            Image(systemName: entry.kind.icon)
                .font(.caption2)
                .foregroundStyle(.secondary)

            VStack(alignment: .leading, spacing: 1) {
                Text(entry.label)
                    .font(.caption)
                    .foregroundStyle(.primary)
                    .lineLimit(1)
                if let detail = entry.detail {
                    Text(detail)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(Color(.controlBackgroundColor))
        .cornerRadius(4)
    }
}

#Preview {
    SourcesLedgerView(entries: [
        SourceLedgerEntry(id: "document:1", kind: .document, label: "Marshall Diary vol. 3", nodeId: "1", detail: "…the survey party reached the lake…"),
        SourceLedgerEntry(id: "research:2", kind: .research, label: "LAC digitised map", nodeId: "2", detail: "https://recherche-collection.bac-lac.gc.ca/…")
    ])
    .frame(width: 380)
}
