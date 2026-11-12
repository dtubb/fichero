import SwiftUI

/// The Segments list's first row (#6415): the page itself, with its kind's icon and what it holds. Clicking it selects
/// the page, so the Inspector shows the page and the Preview selects nothing.
struct SegmentsPageRow: View {
    let row: SegmentsPane.PageRow
    /// Nothing on the page is selected: the Inspector shows the page.
    let selected: Bool
    let select: () -> Void

    var body: some View {
        Button(action: select) {
            HStack(spacing: 6) {
                Image(systemName: "doc")
                    .foregroundStyle(.secondary)
                    .accessibilityHidden(true)
                Text(row.title)
                    .lineLimit(1)
                    .truncationMode(.middle)
                Spacer(minLength: 4)
                Text(row.detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(selected ? Color.secondary.opacity(0.12) : Color.clear)
            .contentShape(.rect)
        }
        .buttonStyle(.plain)
        .help("Show the page in the Inspector")
        .accessibilityLabel("\(row.title), \(row.detail)")
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier("segments.pageRow")
    }
}

#Preview("Segments page row: the page, nothing selected") {
    SegmentsPageRow(row: .init(title: "7_Hoja_4_Recto.JPG", detail: "19 lines, 2 regions"), selected: true) {}
        .frame(width: 320)
}
