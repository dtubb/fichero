import FicheroAPIClient
import SwiftUI

/// How do you want to run this? (`designer.how.*`): four short questions before the stages. Where the work runs
/// (a place the app does not allow is greyed with the engine's reason, never hidden), which kind of model, what
/// matters most, and what you have (shown, not asked). The engine owns the options, the words and the proposed card.
struct RecipeHowFields: View {
    @Bindable var store: RecipeSetupStore
    @State private var suggestions: SuggestionsStore?

    private let mattersWords = ["speed": "Speed", "cost": "Cost", "quality": "Quality", "privacy": "Privacy"]

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            if let asked = store.howQuestions {
                places(asked)
                modelKinds(asked)
                matters(asked)
                if let card = asked.proposedCard {
                    Text("Proposed from your answers: route \(card). You can change it on the next pages.")
                        .font(.caption).foregroundStyle(.secondary)
                        .accessibilityIdentifier("how.proposedCard")
                }
            }
            if let have = store.whatYouHave {
                VStack(alignment: .leading, spacing: 2) {
                    Text("What you have").font(.headline)
                    Text(have).font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                }
                .accessibilityIdentifier("how.whatYouHave")
            }
            if let suggestions { SuggestionRowsView(store: suggestions, page: .how) }
        }
        .task {
            await store.loadHowQuestions()
            await store.loadWhatYouHave()
            if suggestions == nil { suggestions = SuggestionsStore(client: store.client) }
            await suggestions?.load()
        }
    }

    private func places(_ asked: Components.Schemas.HowQuestions) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Where should the work run?").font(.headline)
            ForEach(asked.places, id: \.id) { option in
                VStack(alignment: .leading, spacing: 1) {
                    Toggle(option.name, isOn: Binding(get: { store.isTicked(place: option.id) },
                                                      set: { _ in store.toggle(place: option.id) }))
                        .setupCheckbox()
                        .disabled(!option.allowed)
                        .accessibilityIdentifier("how.place.\(option.id)")
                    Text(option.reason ?? option.consequence).font(.caption).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    private func modelKinds(_ asked: Components.Schemas.HowQuestions) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Which kind of model?").font(.headline)
            let chosen = store.how.modelKind ?? asked.defaultModelKind
            ForEach(asked.modelKinds, id: \.id) { option in
                VStack(alignment: .leading, spacing: 1) {
                    Button { store.setModelKind(option.id) } label: {
                        Label(option.name, systemImage: chosen == option.id ? "largecircle.fill.circle" : "circle")
                    }
                    .buttonStyle(.plain)
                    .disabled(!option.allowed)
                    .accessibilityIdentifier("how.modelKind.\(option.id)")
                    Text(option.reason ?? option.consequence).font(.caption).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    private func matters(_ asked: Components.Schemas.HowQuestions) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("What matters most?").font(.headline)
            let choice = Binding(get: { store.how.matters ?? "" }, set: { store.setMatters($0) })
            Picker("What matters most", selection: choice) {
                ForEach(asked.matters, id: \.self) { id in Text(mattersWords[id] ?? id).tag(id) }
            }
            .pickerStyle(.segmented).labelsHidden()
            .accessibilityIdentifier("how.matters")
        }
    }
}

#Preview("How do you want to run this") {
    RecipeHowFields(store: RecipeSetupStore(client: FicheroClient(libraryPath: nil))).padding().frame(width: 520)
}
