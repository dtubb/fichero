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
            // 2026-08-14 night: "just dates, no transcript").
            if let excerpt = row.excerpt {
                Text(excerpt)
                    .font(.callout)
                    .lineLimit(4)
                    .foregroundStyle(.primary.opacity(0.85))
                    .padding(.top, 2)
            }
            attributeLines(row)
            Spacer(minLength: 0)
        }
        .padding(10)
        .frame(maxWidth: .infinity, minHeight: 110, alignment: .topLeading)
        .background(.quaternary.opacity(0.4), in: RoundedRectangle(cornerRadius: 8))
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
    DatasetCardsView(store: .previewDiary())
        .frame(width: 780, height: 640)
}
