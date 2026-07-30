import SwiftUI

/// One collapsible group of non-document search hits (#4403).
///
/// Entities and claims were searched, returned and counted, but had no
/// renderer — so a search for a person who exists showed only Artifacts. One
/// section type now renders all three legs, which is also why the artifact
/// group moved onto it rather than being copied twice.
///
/// Two things the original artifact group did that are deliberately not
/// carried over:
///
///   - It showed five rows and then "…and N more" as inert text. A count you
///     cannot act on repeats the same failure as this issue one level down —
///     the app saying it found things it will not show you. The overflow is a
///     button that expands the section.
///   - It identified rows by array offset. Results re-rank between queries, so
///     positional identity makes every row re-render and animate wrongly.
///     Rows carry the server's id.
struct SearchHitSection: View {
    let title: String
    let systemImage: String
    let rows: [SearchHitPresentation.Row]
    /// Open the document behind a row. Only called for openable rows.
    let open: (String) -> Void

    @State private var isExpanded = false

    private var visibleRows: [SearchHitPresentation.Row] {
        isExpanded ? rows : Array(rows.prefix(SearchHitPresentation.previewLimit))
    }

    private var hiddenCount: Int {
        max(0, rows.count - visibleRows.count)
    }

    var body: some View {
        if rows.isEmpty {
            EmptyView()
        } else {
            DisclosureGroup {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(visibleRows) { row in
                        rowView(row)
                    }
                    overflowControl
                }
                .padding(.leading, 4)
            } label: {
                Label("\(title) (\(rows.count))", systemImage: systemImage)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(.horizontal, 12)
            .padding(.bottom, 4)
            .background(.bar)
        }
    }

    @ViewBuilder
    private func rowView(_ row: SearchHitPresentation.Row) -> some View {
        Button {
            if let documentId = row.documentId { open(documentId) }
        } label: {
            HStack(spacing: 6) {
                Text(row.badge)
                    .font(.caption2.weight(.medium))
                    .padding(.horizontal, 6)
                    .padding(.vertical, 1)
                    .background(Capsule().fill(Color.secondary.opacity(0.12)))
                Text(row.title)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                Spacer()
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        // A hit with no document behind it stays visible and says why, rather
        // than looking clickable and doing nothing.
        .disabled(!row.isOpenable)
        .help(row.isOpenable ? row.title : SearchHitPresentation.unopenableReason)
        .accessibilityLabel("\(row.badge): \(row.title)")
        .accessibilityHint(
            row.isOpenable ? "Opens the source document" : SearchHitPresentation.unopenableReason
        )
    }

    @ViewBuilder
    private var overflowControl: some View {
        if hiddenCount > 0 {
            Button("Show \(hiddenCount) more") { isExpanded = true }
                .font(.caption2)
                .buttonStyle(.plain)
                .foregroundStyle(.tint)
                .accessibilityHint("Expands this group to show every result")
        } else if isExpanded, rows.count > SearchHitPresentation.previewLimit {
            Button("Show fewer") { isExpanded = false }
                .font(.caption2)
                .buttonStyle(.plain)
                .foregroundStyle(.tint)
        }
    }
}
