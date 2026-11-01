import FicheroAPIClient
import SwiftUI

/// A language question's field: type to find any language (by its name in English or its own, with or without
/// accents); the pick is kept as its tag (`source.onboard.stages.normalise-and-translate`).
struct StageLanguageField: View {
    let store: RecipeSetupStore
    @Binding var answer: StageAnswer?
    @State private var query = ""
    @State private var matches: [RecipeSetupStore.CodeChoice] = []

    private var chosen: String? { if case .text(let tag) = answer, !tag.isEmpty { tag } else { nil } }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let chosen {
                HStack {
                    Text(store.name(of: chosen))
                    Button("Change") { answer = nil }.controlSize(.small)
                }
            } else {
                TextField("Language", text: $query, prompt: Text("Type to find, e.g. English"))
                    .textFieldStyle(.roundedBorder)
                ForEach(matches.prefix(8), id: \.self) { match in
                    Button(match.name) {
                        store.remember(match)
                        answer = .text(match.code)
                        query = ""
                        matches = []
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .task(id: query) {
            let needle = query.trimmingCharacters(in: .whitespaces)
            guard !needle.isEmpty else { matches = []; return }
            try? await Task.sleep(for: .milliseconds(200))
            guard !Task.isCancelled else { return }
            matches = await store.searchLanguages(needle)
        }
    }
}
