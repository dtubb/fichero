import FicheroAPIClient
import SwiftUI

/// The cards of one candidates list in the Models window (`models.search.is-the-finder`,
/// `models.bookmark.kept-not-added`, #6588): one row per card with its name, where it was found, its size, the Usable
/// words and the card's one verb. Every word is `ModelCandidateRules`'s or the engine's; the verbs are the store's.
struct ModelCandidatesListView: View {
    let store: ModelsWindowStore
    let list: ModelCandidateRules.List
    let search: String

    var body: some View {
        let cards = store.cards(list, matching: search)
        List(cards, id: \.id) { card in
            HStack {
                Text(card.name).frame(maxWidth: .infinity, alignment: .leading)
                Text(ModelFinderStore.sourceWords(card.source)).foregroundStyle(.secondary).frame(width: 160, alignment: .leading)
                Text(card.size).frame(width: 90, alignment: .leading)
                Text(ModelCandidateRules.usableWords(store.facts(card))).frame(width: 190, alignment: .leading)
                if let verb = ModelCandidateRules.verb(store.facts(card)) {
                    Button(verb) { Task { await store.press(card) } }
                        .frame(width: 130)
                        .accessibilityIdentifier("models.candidate.verb")
                } else {
                    Color.clear.frame(width: 130, height: 1)
                }
            }
        }
        .overlay {
            if cards.isEmpty {
                ContentUnavailableView(store.finder.errorMessage ?? store.finder.searchLine ?? "Nothing here",
                                       systemImage: "magnifyingglass")
            }
        }
        .accessibilityIdentifier("models.candidates")
    }
}

#Preview("The candidates, in the Models pane") {
    ModelsPaneView()
        .environment(LibraryManager.shared)
        .frame(width: 1100, height: 600)
}
