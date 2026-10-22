import FicheroAPIClient
import SwiftUI
import UniformTypeIdentifiers

/// Languages or scripts, type-to-find only (#5479, ruled 2026-10-05: no Browse… and no
/// alphabetical list): typing shows the engine registry's matches in a dropdown under the field;
/// a pick becomes a token (its name shown, its tag or code saved); several at once; × removes.
/// Return on a typed word takes the engine's best answer (its tag, never the word); a word the
/// engine does not know is refused in words.
struct CodeTokenField: View {
    let store: RecipeSetupStore
    let scripts: Bool
    /// Called after a token is added or removed (the Inspector saves then).
    var onChange: () -> Void = {}
    @State private var query = ""
    @State private var matches: [RecipeSetupStore.CodeChoice] = []

    private var title: String { scripts ? "Writing system" : "Languages" }
    private var codes: [String] { scripts ? store.scripts : store.languages }
    private var unchosen: [RecipeSetupStore.CodeChoice] { matches.filter { !codes.contains($0.code) } }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            LabeledContent(title) {
                field
            }
            // The matches as the person types, under the field, on every platform
            // (`source.onboard.project.language-as-you-type`): the Mac's text-field dropdown did not show them.
            if !unchosen.isEmpty {
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(unchosen.prefix(8), id: \.self) { match in
                        Button { take(RecipeSetupStore.completion(for: match)) } label: { MatchLabel(match: match) }
                            .buttonStyle(.plain)
                    }
                }
                .padding(6)
                .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 6))
            }
            Text(CodeListSource.note(scripts: scripts))
                .font(.caption)
                .foregroundStyle(.secondary)
            if let refusal = store.typedRefusal, refusal.scripts == scripts {
                Label(refusal.text, systemImage: "exclamationmark.triangle").font(.caption).foregroundStyle(.orange)
            }
            if !codes.isEmpty {
                FlowTokens(codes: codes, name: store.name(of:)) { code in
                    store.remove(code, fromScripts: scripts)
                    onChange()
                }
            }
        }
        .task(id: query) {
            let needle = query.trimmingCharacters(in: .whitespaces)
            guard !needle.isEmpty else { matches = []; return }
            // A pick puts its completion in the field; that is not a new search.
            guard !unchosen.contains(where: { RecipeSetupStore.completion(for: $0) == needle }) else { return }
            try? await Task.sleep(for: .milliseconds(200))  // typing: ask once the person pauses
            guard !Task.isCancelled else { return }
            matches = scripts ? await store.searchScripts(needle) : await store.searchLanguages(needle)
        }
    }

    private var field: some View {
        TextField(title, text: $query, prompt: Text(scripts ? MaterialPrompts.writingSystem : MaterialPrompts.languages))
            .labelsHidden()
            .onChange(of: query) { _, text in take(text) }
            .onSubmit {
                let typed = query
                if take(typed) { return }
                Task {
                    if await store.addTyped(typed, toScripts: scripts) {
                        clear()
                        onChange()
                    }
                }
            }
    }

    /// A match picked in the dropdown becomes a token and the field clears.
    @discardableResult
    private func take(_ text: String) -> Bool {
        guard store.pick(text, among: matches, toScripts: scripts) else { return false }
        clear()
        onChange()
        return true
    }

    private func clear() {
        query = ""
        matches = []
    }
}

/// One match in the dropdown: its name, and where it came from (a dialect's language, a code).
private struct MatchLabel: View {
    let match: RecipeSetupStore.CodeChoice

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(match.name)
            if let detail = match.detail { Text(detail).font(.caption).foregroundStyle(.secondary) }
        }
    }
}

/// The chosen languages or scripts as blue lozenges, each with its name (its tag on hover) and ×.
private struct FlowTokens: View {
    let codes: [String]
    let name: (String) -> String
    let remove: (String) -> Void

    var body: some View {
        // Wraps: many languages in one row must not widen the sheet (#5624).
        FlowLayout(spacing: 6) {
            ForEach(codes, id: \.self) { code in
                HStack(spacing: 4) {
                    Text(name(code))
                    Button { remove(code) } label: {
                        Image(systemName: "xmark.circle.fill")
                    }
                    .buttonStyle(.borderless)
                    .accessibilityLabel("Remove \(name(code))")
                }
                .font(.body)
                .foregroundStyle(.white)
                .padding(.horizontal, 8)
                .padding(.vertical, 3)
                .background(Color.accentColor, in: Capsule())
                .help(code)
            }
        }
    }
}

#Preview("Languages and writing systems") {
    let store = RecipeSetupStore(client: FicheroClient(libraryPath: nil))
    store.languages = ["es", "la"]
    store.scripts = ["Latn"]
    return VStack(alignment: .leading, spacing: 12) {
        CodeTokenField(store: store, scripts: false)
        CodeTokenField(store: store, scripts: true)
    }
    .padding()
    .frame(width: 360)
}
