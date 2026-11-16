import FicheroAPIClient
import SwiftUI

/// The suggestions for one page, each with its reason and Change… (`wide.suggest.reason-and-override`). The words are the engine's;
/// this lays them out. A suggestion is a row, never a dialog, and it does nothing by itself.
struct SuggestionRowsView: View {
    let store: SuggestionsStore
    let page: SuggestionPage
    /// Change… on a row: the page's own control for it (the caller opens or focuses it).
    var onChange: (SuggestionRow) -> Void = { _ in }

    var body: some View {
        let rows = store.rows(on: page)
        if !rows.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                ForEach(rows) { row in
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        VStack(alignment: .leading, spacing: 2) {
                            HStack(spacing: 6) {
                                Text(row.what).font(.callout)
                                if row.yours { Text(SuggestionRow.yoursWords).font(.caption).foregroundStyle(Color.accentColor) }
                                if let price = row.price { Text(price).font(.caption).foregroundStyle(.secondary) }
                            }
                            Text(row.reasonLine).font(.caption).foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        Spacer(minLength: 8)
                        Button("Change…") { store.markChanged(row.id); onChange(row) }
                            .accessibilityIdentifier("suggestion.change.\(row.id)")
                    }
                    .accessibilityElement(children: .contain)
                    .accessibilityIdentifier("suggestion.row.\(row.id)")
                }
            }
        }
    }
}

#Preview("Suggestions on a stage page") {
    let rows = [
        SuggestionRow(id: "leave-out", what: "Leave out what is not writing before reading",
                      why: "4 of 5 sample pages have marks that are not writing", from: "the sample's own findings",
                      change: "stage.leave-out", price: "free"),
        SuggestionRow(id: "review", what: "Turn Review on", why: "A large reader may invent text", from: "model kind: large",
                      change: "stage.review", yours: true)
    ]
    let store = SuggestionsStore(client: FicheroClient(libraryPath: nil), rows: rows)
    SuggestionRowsView(store: store, page: .stage(jobs: ["leave-out", "review"]))
        .padding().frame(width: 520)
}
