import FicheroAPIClient
import SwiftUI

/// The search model a project uses, in the Inspector's project section, and "Change embedding model…"
/// (`search.embedding.change-is-a-re-embed-run`, #6122): the sheet shows what the change would cost before the person
/// starts it.
struct InspectorProjectEmbedding: View {
    let library: LibraryManager.LibraryReference
    @State private var store: EmbeddingChangeStore?
    @State private var changing = false

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let current = store?.current {
                Text("Search model: \(EmbeddingModelChoice.name(of: current.model))\(vectorsWords(current))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Button("Change embedding model…") { changing = true }
                .controlSize(.small)
                .disabled(store == nil)
        }
        .task {
            let made = EmbeddingChangeStore(client: library.ficheroClient)
            store = made
            await made.load()
        }
        .sheet(isPresented: $changing) {
            if let store {
                EmbeddingChangeSheet(store: store, done: { changing = false })
            }
        }
    }

    private func vectorsWords(_ current: Components.Schemas.EmbeddingChoiceResponse) -> String {
        current.vectors == 0 ? "" : " · \(current.vectors) vectors"
    }
}

/// Choose the model, read the plan, start the run. Nothing runs until "Embed every page again".
struct EmbeddingChangeSheet: View {
    let store: EmbeddingChangeStore
    let done: () -> Void
    @State private var model = ""

    private var others: [EmbeddingModelChoice] {
        EmbeddingModelChoice.all.filter { $0.model != store.current?.model }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Change embedding model").font(.headline)
            Text("Search finds pages by meaning with the model the project was made with. A different model means embedding "
                 + "every page again; vectors from two models are never mixed. Search keeps using the old ones until the "
                 + "new ones are all made.")
                .font(.callout)
            Picker("New model", selection: $model) {
                ForEach(others) { choice in
                    Text(choice.name).tag(choice.model)
                }
            }
            if let plan = store.plan {
                Text(EmbeddingChangeStore.sentence(for: plan))
                if let started = store.started {
                    Label(started.message, systemImage: "checkmark.circle")
                }
            }
            if let error = store.errorMessage {
                Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
            }
            HStack {
                Spacer()
                Button(store.started == nil ? "Cancel" : "Done", action: done)
                    .keyboardShortcut(.cancelAction)
                if store.started == nil {
                    Button("Embed every page again") { Task { await store.start() } }
                        .keyboardShortcut(.defaultAction)
                        .disabled(store.plan == nil || store.plan?.same == true || store.isBusy)
                }
            }
        }
        .padding()
        .frame(width: 440)
        .task(id: model) {
            if model.isEmpty { model = others.first?.model ?? "" }
            if !model.isEmpty { await store.loadPlan(for: model) }
        }
    }
}

#Preview("Change embedding model") {
    EmbeddingChangeSheet(store: EmbeddingChangeStore(client: FicheroClient(libraryPath: nil)), done: {})
}
