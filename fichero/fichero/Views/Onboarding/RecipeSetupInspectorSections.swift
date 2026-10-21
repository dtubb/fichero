import FicheroAPIClient
import SwiftUI

/// One topic's explanation as the registry wrote it (`source.onboard.topics-written-once`): its
/// one sentence, and with `full` its paragraph and example as plain text, never behind a
/// disclosure. Setup and the Inspector show a topic only through this, so the words are the
/// registry's, never the app's.
struct TopicExplanation: View {
    let topic: Components.Schemas.TopicInfo
    var full = false

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            if full {
                Text(topic.long).font(.caption)
                if let example = topic.example {
                    Label(example, systemImage: "doc.text.magnifyingglass")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            } else {
                Text(topic.short).font(.body)
            }
        }
        .textSelection(.enabled)
    }
}

/// The Inspector's recipe section: the recipe setup proposed for THIS project, and Set Up…, which
/// asks the window to open setup for it (`LibraryManager.requestSetUp`), one code path
/// (`source.onboard.set-up-later`, `source.onboard.edited-in-the-inspector`).
struct InspectorRecipeSection: View {
    let library: LibraryManager.LibraryReference?
    @Environment(LibraryManager.self) private var libraryManager

    var body: some View {
        if let library {
            let store = library.recipeSetupStore
            VStack(alignment: .leading, spacing: 6) {
                if let recipe = store.recipe {
                    RecipeStepsView(store: store, recipe: recipe)
                } else {
                    Text("No recipe yet. Setup proposes one from your purposes and material.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                InspectorProjectLanguages(store: store)
                InspectorProjectLayers(store: store)
                Button("Set Up…") { libraryManager.requestSetUp(for: library.id) }
                    .controlSize(.small)
            }
            // Each step's name and explanation (the job and topic registries).
            .task { await store.loadJobs() }
        }
    }
}

/// A language added (or removed) after setup, from the Inspector
/// (`source.onboard.add-layer`): the recipe is proposed again from the new
/// answers and both are kept on the project. Nothing runs until Start.
struct InspectorProjectLanguages: View {
    let store: RecipeSetupStore

    var body: some View {
        CodeTokenField(store: store, scripts: false) {
            Task { await store.updateLanguages(store.languages) }
        }
        .font(.caption)
        // Edit what the project saved, never the defaults over it.
        .task { await store.loadSaved() }
    }
}

/// A layer added (or removed) after setup, from the Inspector (`source.onboard.add-layer`):
/// the engine adds its steps to the recipe and proposes its jobs for the pages already there;
/// this shows those jobs, each explained by its topic, with the estimate, and Start runs them
/// through the same Start as setup. Nothing runs before Start.
struct InspectorProjectLayers: View {
    let store: RecipeSetupStore

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(store.layers, id: \.self) { layer in
                HStack {
                    Label(layer.capitalized, systemImage: "square.3.layers.3d")
                    Spacer()
                    Button("Remove") { Task { await store.changeLayer(layer, remove: true) } }
                        .controlSize(.small)
                }
            }
            Menu("Add a Layer…") {
                ForEach(store.addableLayers, id: \.self) { layer in
                    Button(layer.capitalized) { Task { await store.changeLayer(layer) } }
                }
            }
            .controlSize(.small)
            .disabled(store.addableLayers.isEmpty)
            if let proposed = store.proposedJobs, let plan = store.startPlan {
                proposal(proposed, plan: plan)
            }
        }
        .font(.caption)
        .task {
            await store.loadJobs()
            await store.loadStartPlan()
        }
    }

    private func proposal(_ proposed: Components.Schemas.ProposedJobs,
                          plan: Components.Schemas.StartPlan) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("For the pages already here: \(plan.estimate.pages) pages · \(RecipeStartFields.cost(plan.estimate.totalCostUsd))")
                .font(.body)
            ForEach(proposed.steps, id: \.step) { step in
                VStack(alignment: .leading, spacing: 2) {
                    Text(step.title).bold()
                    if let topic = store.topics.topic(step.topic) {
                        TopicExplanation(topic: topic)
                    } else {
                        Text(step.explanation).foregroundStyle(.secondary)
                    }
                }
            }
            ForEach(plan.refusals, id: \.self) { refusal in
                Label(refusal, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
            }
            Button("Start") { Task { await store.start() } }
                .disabled(!store.canStart)
                .help(store.startDisabledReason ?? "Run what these layers propose on the material already here")
            if let message = store.errorMessage {
                Text(message).foregroundStyle(.red)
            }
        }
    }
}

#Preview("Project layers") {
    let store = RecipeSetupStore(client: FicheroClient(libraryPath: nil))
    return InspectorProjectLayers(store: store)
        .padding()
        .frame(width: 320)
}

#Preview("Project languages") {
    let store = RecipeSetupStore(client: FicheroClient(libraryPath: nil))
    store.languages = ["es", "la"]
    return InspectorProjectLanguages(store: store)
        .padding()
        .frame(width: 320)
}

#Preview("Recipe steps") {
    let store = RecipeSetupStore(client: FicheroClient(libraryPath: nil))
    let recipe = Components.Schemas.AssembledRecipe(
        id: "generated",
        title: "Spanish handwriting",
        purposes: ["transcribe"],
        steps: [
            .init(
                id: "lines", job: "find-lines", title: "Find lines",
                sentence: "Finds each line of writing on the page.",
                card: .init(id: "kraken:builtin/blla@bundled", note: "Kraken's built-in line finder",
                            licence: "Apache-2.0", sizeGb: 0.01, memoryGb: 3.6, trainable: true),
                usesCloud: false, runsOn: "this-mac",
                reasons: ["ships inside the app"], layer: "lines"
            ),
            .init(
                id: "correct", job: "correct", title: "Correct",
                sentence: "A language model corrects the reading.",
                reasons: [], gap: "no local corrector knows es",
                problem: .init(kind: "no-model-for-language", sentence: "No correcting model here knows Spanish yet.",
                               fix: "download", fixes: ["download", "choose-cloud"],
                               detail: "mlx:Qwen/Qwen2.5-3B@main: languages [en] lack es")
            )
        ],
        gaps: ["correct: no local corrector knows es"],
        cloudOptions: ["correct"],
        problems: []
    )
    return ScrollView {
        RecipeStepsView(store: store, recipe: recipe, onFix: { _ in }).padding()
    }
    .frame(width: 480, height: 520)
}
