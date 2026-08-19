import SwiftUI

/// One flat group of non-document search hits (#4403, reshaped for #4604).
///
/// Entities and claims were searched, returned and counted, but had no
/// renderer — so a search for a person who exists showed only Artifacts. One
/// section type renders all three legs.
///
/// Daniel's ruling (2026-08-19, #4604): NO disclosure triangle, NO
/// preview-cap — "we don't want any of that. We want entities and artifacts
/// to appear like nodes in the search result." Every hit renders as a
/// full-width row, always visible, styled like a result rather than a
/// footnote. (Making them literal library NODES usable in every view mode is
/// #4118's design; this kills the hidden-behind-a-triangle presentation
/// today.)
///
/// Rows carry the server's id, never array offsets — results re-rank between
/// queries, and positional identity makes every row re-render and animate
/// wrongly.
struct SearchHitSection: View {
    let title: String
    let systemImage: String
    let rows: [SearchHitPresentation.Row]
    /// Open the document behind a row. Only called for openable rows.
    let open: (String) -> Void

    var body: some View {
        if rows.isEmpty {
            EmptyView()
        } else {
            VStack(alignment: .leading, spacing: 2) {
                Label("\(title) (\(rows.count))", systemImage: systemImage)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .padding(.bottom, 2)
                ForEach(rows) { row in
                    rowView(row)
                }
            }
            .padding(.horizontal, 12)
            .padding(.bottom, 6)
            .background(.bar)
        }
    }

    @ViewBuilder
    private func rowView(_ row: SearchHitPresentation.Row) -> some View {
        Button {
            if let documentId = row.documentId { open(documentId) }
        } label: {
            HStack(spacing: 8) {
                Image(systemName: systemImage)
                    .foregroundStyle(.secondary)
                    .imageScale(.small)
                Text(row.title)
                    .font(.callout)
                    .lineLimit(1)
                Spacer(minLength: 4)
                Text(row.badge)
                    .font(.caption2.weight(.medium))
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 1)
                    .background(Capsule().fill(Color.secondary.opacity(0.12)))
            }
            .padding(.vertical, 3)
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
}
