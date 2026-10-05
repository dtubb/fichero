import FicheroAPIClient
import SwiftUI

/// An assembled recipe, step by step: what each step does (the topic registry's
/// own words, `TopicStore`), why the rules chose it, what is missing, and an Advanced
/// disclosure with the model and settings (`source.onboard.proposes-chain`,
/// `source.onboard.self-documenting`, `source.onboard.says-no-model`,
/// `source.recipe.advanced-per-step`). Shared by setup and the Inspector so both
/// explain a step the same way.
struct RecipeStepsView: View {
    let store: RecipeSetupStore
    let recipe: Components.Schemas.AssembledRecipe

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if recipe.steps.isEmpty {
                Text("Nothing runs by itself for this purpose. Every tool stays on hand to run when you choose.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
            ForEach(recipe.steps, id: \.id) { step in
                RecipeStepRow(step: step, title: store.title(of: step), job: store.job(for: step),
                              explanation: store.explanation(ofJob: step.job))
            }
            ForEach(recipe.gaps, id: \.self) { gap in
                Label(gap, systemImage: "exclamationmark.triangle")
                    .font(.callout)
                    .foregroundStyle(.orange)
            }
            ForEach(recipe.problems, id: \.self) { problem in
                Label(problem, systemImage: "xmark.octagon")
                    .font(.callout)
                    .foregroundStyle(.red)
            }
        }
    }
}

private struct RecipeStepRow: View {
    let step: Components.Schemas.RecipeStep
    let title: String
    let job: Components.Schemas.JobInfo?
    let explanation: Components.Schemas.TopicInfo?

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline) {
                Text(title).font(.headline)
                if let layer = step.layer ?? job?.layer {
                    Text(layer).font(.caption).foregroundStyle(.secondary)
                }
            }
            if let explanation {
                TopicExplanation(topic: explanation)
            }
            if let card = step.card {
                Label(Self.cardSummary(card), systemImage: step.usesCloud == true ? "cloud" : "desktopcomputer")
                    .font(.callout)
            }
            if let gap = step.gap {
                Label("Needs a model: \(gap)", systemImage: "exclamationmark.triangle")
                    .font(.callout)
                    .foregroundStyle(.orange)
            }
            ForEach(step.reasons ?? [], id: \.self) { reason in
                Label(reason, systemImage: "checkmark.circle")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            DisclosureGroup("Advanced") {
                VStack(alignment: .leading, spacing: 2) {
                    if let runsOn = step.runsOn { row("Runs on", runsOn) }
                    if let card = step.card {
                        row("Card", card.id)
                        if let memory = card.memoryGb { row("Memory", "\(memory.formatted()) GB") }
                        if let published = card.cerPublished { row("Error rate (published)", Self.percent(published)) }
                        if let trainable = card.trainable { row("Trainable", trainable ? "Yes" : "No") }
                    }
                    pairs("Model", step.model?.additionalProperties.value)
                    pairs("Setting", step.settings?.additionalProperties.value)
                    pairs("Offered when", step.offeredWhen?.additionalProperties.value)
                    if let job {
                        row("Takes", job.takes.joined(separator: ", "))
                        row("Gives", job.gives.joined(separator: ", "))
                        row("Compared by", job.compare)
                    }
                }
            }
            .font(.caption)
        }
        .padding(.vertical, 4)
    }

    /// The card's note as the model's name, then licence, download size and
    /// the error rate measured here (or else the published one).
    static func cardSummary(_ card: Components.Schemas.RecipeCard) -> String {
        var parts = [card.note ?? card.id]
        if let licence = card.licence { parts.append(licence) }
        if let size = card.sizeGb { parts.append("\(size.formatted()) GB") }
        if let cer = card.cerMeasuredHere {
            parts.append("\(percent(cer)) errors on your pages")
        } else if let cer = card.cerPublished {
            parts.append("\(percent(cer)) errors (published)")
        }
        return parts.joined(separator: " · ")
    }

    static func percent(_ rate: Double) -> String {
        rate.formatted(.percent.precision(.fractionLength(0...1)))
    }

    private func row(_ label: String, _ value: String) -> some View {
        LabeledContent(label) { Text(value).textSelection(.enabled) }
    }

    @ViewBuilder
    private func pairs(_ label: String, _ values: [String: (any Sendable)?]?) -> some View {
        if let values {
            ForEach(values.keys.sorted(), id: \.self) { key in
                row("\(label) · \(key)", values[key].flatMap { $0 }.map { String(describing: $0) } ?? "—")
            }
        }
    }
}

/// One topic's explanation as the registry wrote it (`source.onboard.topics-written-once`):
/// its one sentence, and its paragraph and example on disclosure. Setup and the Inspector
/// show a topic only through this, so the words are the registry's, never the app's.
struct TopicExplanation: View {
    let topic: Components.Schemas.TopicInfo

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(topic.short).font(.callout)
            DisclosureGroup("More") {
                VStack(alignment: .leading, spacing: 4) {
                    Text(topic.long)
                    if let example = topic.example {
                        Label(example, systemImage: "doc.text.magnifyingglass")
                            .foregroundStyle(.secondary)
                    }
                }
                .font(.caption)
                .textSelection(.enabled)
            }
            .font(.caption)
        }
    }
}

/// The Inspector's recipe section: the recipe setup proposed, and Set Up…,
/// which opens first run's own recipe steps (`FirstRunStep.setUpSteps`), one
/// code path (`source.onboard.set-up-later`, `source.onboard.edited-in-the-inspector`).
struct InspectorRecipeSection: View {
    @Environment(AppState.self) private var appState: AppState?
    @State private var showingSetup = false

    var body: some View {
        if let appState {
            VStack(alignment: .leading, spacing: 6) {
                if let recipe = appState.recipeSetupStore.recipe {
                    RecipeStepsView(store: appState.recipeSetupStore, recipe: recipe)
                } else {
                    Text("No recipe yet. Setup proposes one from your purpose and material.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                InspectorProjectLanguages(store: appState.recipeSetupStore)
                InspectorProjectLayers(store: appState.recipeSetupStore)
                Button("Set Up…") { showingSetup = true }
                    .controlSize(.small)
            }
            .sheet(isPresented: $showingSetup) {
                FirstRunWindow(setUp: true)
                    .environment(appState)
            }
            // Each step's name and explanation (the job and topic registries).
            .task { await appState.recipeSetupStore.loadJobs() }
        }
    }
}

/// A language added (or removed) after setup, from the Inspector
/// (`source.onboard.add-layer`): the recipe is proposed again from the new
/// answers and both are kept on the project. Nothing runs until Start.
struct InspectorProjectLanguages: View {
    let store: RecipeSetupStore

    var body: some View {
        CodeSearchField(
            title: "Languages",
            prompt: "Add a language: name, BCP 47 tag or glottocode",
            search: store.searchLanguages,
            codes: Binding(
                get: { store.languages },
                set: { codes in Task { await store.updateLanguages(codes) } }
            )
        )
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
                .font(.callout)
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
                id: "lines", job: "find-lines",
                card: .init(id: "kraken:builtin/blla@bundled", note: "Kraken's built-in line finder",
                            licence: "Apache-2.0", sizeGb: 0.01, memoryGb: 3.6, trainable: true),
                usesCloud: false, runsOn: "this-mac",
                reasons: ["ships inside the app"], layer: "lines"
            ),
            .init(
                id: "read", job: "read-a-line",
                card: .init(id: "kraken:zenodo/10.5281/zenodo.13788177@unpinned",
                            note: "McCATMuS, general Latin-script recognition",
                            licence: "CC-BY-4.0", sizeGb: 0.016, cerPublished: 0.0391),
                usesCloud: false, runsOn: "this-mac",
                reasons: ["covers Latn", "runs on this Mac"], layer: "reading"
            ),
            .init(id: "correct", job: "correct", reasons: [], gap: "no local corrector knows es")
        ],
        gaps: ["correct: no local corrector knows es"],
        cloudOptions: ["correct"],
        problems: []
    )
    return ScrollView {
        RecipeStepsView(store: store, recipe: recipe).padding()
    }
    .frame(width: 480, height: 520)
}
