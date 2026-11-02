import FicheroAPIClient
import SwiftUI

/// "What condition are the pages in?" under the kind of material (`designer.material.condition-asked`): tick boxes, none ticked by
/// default, from the engine's one list, each with one line saying what Fichero does about it. What the sample suggests is a row below,
/// never a tick made for the person.
struct RecipeConditionFields: View {
    @Bindable var store: RecipeSetupStore
    var suggestions: SuggestionsStore?

    var body: some View {
        if !store.conditionOptions.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text("What condition are the pages in?").font(.headline)
                ForEach(store.conditionOptions) { option in
                    VStack(alignment: .leading, spacing: 1) {
                        Toggle(option.name, isOn: Binding(get: { store.isTicked(condition: option.id) },
                                                          set: { _ in store.toggle(condition: option.id) }))
                            .setupCheckbox()
                            .accessibilityIdentifier("condition.\(option.id)")
                        Text(option.help).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                    }
                }
                if let suggestions {
                    SuggestionRowsView(store: suggestions, page: .aboutTheMaterial) { row in
                        // Change… on a suggested condition ticks it: the person's own choice, then labelled yours.
                        if let id = row.id.split(separator: ".").last.map(String.init), row.id.hasPrefix("condition."),
                           !store.isTicked(condition: id) { store.toggle(condition: id) }
                    }
                }
            }
            .accessibilityIdentifier("aboutTheMaterial.condition")
        }
    }
}

#Preview("Condition of the pages") {
    let store = RecipeSetupStore(client: FicheroClient(libraryPath: nil))
    store.conditionOptions = [
        ConditionOption(id: "faded", name: "Faded ink", help: "Fichero raises the contrast of the faded pages before it finds the lines."),
        ConditionOption(id: "stains", name: "Stains", help: "Fichero reads through them and asks a second model to check the lines they touch.")
    ]
    return RecipeConditionFields(store: store).padding().frame(width: 520)
}
