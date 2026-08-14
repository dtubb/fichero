import SwiftUI

// MARK: - Cards renderer (datasets Stage 2)

/// A grid of cards: title role (or node name) as headline, subtitle role as
/// caption, then every declared attribute with a value as a labeled line.
struct DatasetCardsView: View {
    let store: DatasetModeStore
    var onOpen: (DatasetPage.Row) -> Void = { _ in }

    private let columns = [GridItem(.adaptive(minimum: 220, maximum: 320), spacing: 12)]

    var body: some View {
        ScrollView {
            LazyVGrid(columns: columns, spacing: 12) {
                ForEach(store.page?.rows ?? []) { row in
                    card(row)
                        .onTapGesture(count: 2) { onOpen(row) }
                        // Touch parity: iPad has no double-click.
                        .contextMenu { Button("Open") { onOpen(row) } }
                }
            }
            .padding(12)
        }
    }

    private func card(_ row: DatasetPage.Row) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(titleText(row))
                .font(.headline)
                .lineLimit(2)
            if let subtitleAttr = store.attributeForRole["subtitle"],
               let subtitle = store.text(subtitleAttr, of: row) {
                Text(subtitle)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
            attributeLines(row)
            Spacer(minLength: 0)
        }
        .padding(10)
        .frame(maxWidth: .infinity, minHeight: 110, alignment: .topLeading)
        .background(.quaternary.opacity(0.4), in: RoundedRectangle(cornerRadius: 8))
        .contentShape(Rectangle())
    }

    /// The title role names the card; the node NAME is the fallback, and when
    /// the title role duplicated the name it is not repeated.
    private func titleText(_ row: DatasetPage.Row) -> String {
        guard let titleAttr = store.attributeForRole["title"],
              let title = store.text(titleAttr, of: row) else { return row.name }
        return title
    }

    @ViewBuilder
    private func attributeLines(_ row: DatasetPage.Row) -> some View {
        let titleAttr = store.attributeForRole["title"]
        let subtitleAttr = store.attributeForRole["subtitle"]
        let names = store.declaredAttributes
            .filter { $0 != titleAttr && $0 != subtitleAttr }
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
