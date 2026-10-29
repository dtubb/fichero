import FicheroAPIClient
import SwiftUI

/// What the Prepare Images card shows besides its questions: the engine's sentence naming the operations, an answer
/// suggested from five sample pages ("3 of 5 pages agree") with a Use button, and the time line
/// (`prep.setup.three-questions-suggested-from-a-sample`, `prep.estimate.time-on-this-mac-before-start`). The engine
/// writes every word; this view only lays them out (`GET /api/recipes/prepare-images/facts`).
struct PrepareImagesCard: View {
    let store: RecipeSetupStore

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let facts = store.prepareFacts {
                if !facts.howItWorks.isEmpty {
                    Text(facts.howItWorks).font(.callout).fixedSize(horizontal: false, vertical: true)
                }
                ForEach(facts.suggestions.additionalProperties.keys.sorted(), id: \.self) { key in
                    if let suggestion = facts.suggestions.additionalProperties[key] {
                        HStack {
                            Text("Suggested: \(suggestion.why) (\(suggestion.agree) pages)")
                                .font(.caption).foregroundStyle(.secondary)
                            Spacer()
                            Button("Use") {
                                if let answer = StageAnswer.from(suggestion.value.value) {
                                    store.jobAnswers[question: key] = answer
                                }
                            }
                            .controlSize(.small)
                            .accessibilityIdentifier("prepareImages.use.\(key)")
                        }
                    }
                }
                Text(facts.estimate)
                    .font(.caption).foregroundStyle(.secondary)
                    .accessibilityIdentifier("prepareImages.estimate")
            }
        }
        .task { await store.loadPrepareFacts() }
    }
}

#Preview("Prepare Images card") {
    let store = RecipeSetupStore(client: FicheroClient(libraryPath: nil))
    store.prepareFacts = .init(
        suggestions: .init(additionalProperties: [
            "the_paper": .init(value: .init(["ruled"]), agree: "4 of 5", why: "the sample shows ruled paper")
        ]),
        estimate: "About 2 min for 374 pages on this Mac (estimate). Nothing leaves this Mac.",
        howItWorks: "Finds each page, squares it, turns it upright and straightens it.")
    return PrepareImagesCard(store: store).padding().frame(width: 420)
}
