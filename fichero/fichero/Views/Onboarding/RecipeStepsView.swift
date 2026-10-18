import FicheroAPIClient
import SwiftUI

/// An assembled recipe, one row per step (`source.onboard.proposes-chain`,
/// `source.onboard.self-documenting`, `source.onboard.says-no-model`, #5481): the step's title,
/// its one sentence, where it runs and the model by its card's name, never its id. A step that
/// cannot run says so once, in the engine's sentence, with its fix as a button. No disclosure:
/// in setup nothing hides behind More or Advanced; the Inspector shows, as plain lines, the
/// topic's paragraph and the rules' own reason (`problem.detail`), which setup never shows.
/// Shared by setup and the Inspector so both name a step the same way.
struct RecipeStepsView: View {
    let store: RecipeSetupStore
    let recipe: Components.Schemas.AssembledRecipe
    /// A problem's fix button was pressed; nil in the Inspector, which shows the reason instead.
    var onFix: ((String) -> Void)?
    /// Check on your pages, shown under the reading step (#4951); nil where there is no project.
    var bakeoff: BakeoffSection.Context?
    /// The project whose model finder opens beside a reading step's model in setup (#5611,
    /// `source.find.app-finder-three-hosts`); nil where there is no project, or in the Inspector.
    var finder: LibraryManager.LibraryReference?
    /// Only these jobs' steps: a stage page shows its own steps of the plan (section 7c); nil shows every step.
    var onlyJobs: Set<String>?
    /// A step's model candidates, by step id, where the page has read them (a stage page's main step): the step's
    /// card then says whether its model fits this Mac (#5641). Nil, or an empty list: no fit line.
    var candidatesOf: ((String) -> [Components.Schemas.ModelCandidate])?

    @State private var findingFor: FinderStep?
    /// The step whose Review the licence… was pressed (#5660).
    @State private var reviewingLicence: FinderStep?

    /// The step Find a Reader… was pressed beside.
    struct FinderStep: Identifiable {
        let id: String
        let job: String
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if recipe.steps.isEmpty {
                Text("Nothing runs by itself for this purpose. Every tool stays on hand to run when you choose.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
            ForEach(recipe.steps.filter { onlyJobs?.contains($0.job) ?? true }, id: \.id) { step in
                let fit = CandidateFit.ofStep(card: step.card?.id, in: candidatesOf?(step.id) ?? [])
                RecipeStepRow(lines: Self.lines(for: step, store: store, inSetup: onFix != nil, fit: fit),
                              explanation: onFix == nil ? store.explanation(ofJob: step.job) : nil,
                              onFix: fixHandler(for: step),
                              useSmaller: useSmaller(for: step))
                if onFix != nil, let words = store.lastRunWords(stepId: step.id) {  // Ready: what the last run left (#5616)
                    Label(words, systemImage: "arrow.clockwise").font(.callout).foregroundStyle(.secondary)
                }
                if onFix != nil { planEditControls(for: step) }  // Ready only: take a step out (#5627)
                if onFix != nil, finder != nil, store.readsMaterial(step.job) {
                    Button("Find a Reader…") { findingFor = FinderStep(id: step.id, job: step.job) }
                        .controlSize(.small)
                        .help("The readers for this project's scripts and languages, and where to get them")
                }
                // Each step with a comparison offers it: the readers under the reading step, the line finders
                // under Find lines (#5660 item 7).
                if let context = bakeoff?.forStep(step.job) {
                    BakeoffSection(context: context, setup: store)
                }
            }
            // The recipe's own check, in the rules' words: the Inspector only.
            if onFix == nil {
                ForEach(recipe.problems, id: \.self) { problem in
                    Label(problem, systemImage: "xmark.octagon")
                        .font(.caption)
                        .foregroundStyle(.red)
                }
            }
        }
        .sheet(item: $findingFor) { step in
            if let finder {
                ModelFinderSheet(project: finder, setup: store, step: step) { findingFor = nil }
            }
        }
        .sheet(item: $reviewingLicence) { step in
            if let finder {
                LicenceReviewSheet(finder: finder.modelFinderStore, setup: store, step: step) { reviewingLicence = nil }
            }
        }
    }

    /// Use <name> instead on the step's card (#5641): the smaller build through the use-candidate route; setup only.
    private func useSmaller(for step: Components.Schemas.RecipeStep) -> ((CandidateFit.Smaller) -> Void)? {
        guard onFix != nil else { return nil }
        let setup = store
        return { smaller in Task { await setup.useCard(smaller.card, named: smaller.name, forStep: step.id) } }
    }

    /// A step problem's fix button (#5619, #5660): a model fix opens the model finder for THIS step's job, a
    /// licence its review (`LicenceReviewSheet`), letting pages leave goes to setup's own handler; without a
    /// project every fix goes to setup's handler.
    private func fixHandler(for step: Components.Schemas.RecipeStep) -> ((String) -> Void)? {
        guard let onFix else { return nil }
        return { fix in
            let route = Self.fixRoute(fix, hasProject: finder != nil), here = FinderStep(id: step.id, job: step.job)
            if route == .finder { findingFor = here } else if route == .licence { reviewingLicence = here } else { onFix(fix) }
        }
    }
}

extension RecipeStepsView {
    /// One line of a step's row: what the person reads, in order. The row draws exactly these,
    /// so what a step says can be checked without drawing it.
    enum StepLine: Equatable {
        case title(String)
        case sentence(String)
        /// Where it runs, and the model by its card's name.
        case place(String, cloud: Bool)
        /// The step's problem, once, in the engine's sentence.
        case problem(String)
        /// The problem's fix, as a button (setup).
        case fix(title: String, fix: String)
        /// One run per ticked reading level, named (`source.recipe.into-what-is-a-multi-select`).
        case runs(String)
        /// The rules' own reason, model ids included (the Inspector only).
        case detail(String)
        /// Whether the step's model fits this Mac, with the engine's reason (#5641).
        case fit(CandidateFit)
    }

    /// What a step's row says: in setup its title, one sentence, and either its problem once
    /// with the fix as a button, or where it runs; in the Inspector the rules' reason in place of
    /// the button.
    static func lines(for step: Components.Schemas.RecipeStep, store: RecipeSetupStore, inSetup: Bool,
                      fit: CandidateFit? = nil) -> [StepLine] {
        var lines: [StepLine] = [.title(store.title(of: step))]
        if let sentence = store.sentence(of: step) { lines.append(.sentence(sentence)) }
        if let problem = step.problem {
            lines.append(.problem(problem.sentence))
            lines.append(inSetup ? .fix(title: RecipeStepRow.fixTitle(problem.fix), fix: problem.fix) : .detail(problem.detail))
        } else if let place = RecipeStepRow.whereItRuns(step) {
            lines.append(.place(place, cloud: step.usesCloud == true))
        }
        // The engine names the Normalise step's runs (`run_titles`, #5795); the app keeps no list of its own.
        if let runs = runsLine(step.runTitles ?? []) { lines.append(.runs(runs)) }
        if let fit { lines.append(.fit(fit)) }
        return lines
    }

    /// "2 runs: As written · Modernised" when a step writes more than one reading; nil for one.
    static func runsLine(_ titles: [String]) -> String? {
        titles.count > 1 ? "\(titles.count) runs: " + titles.joined(separator: " · ") : nil
    }
}

struct RecipeStepRow: View {
    let lines: [RecipeStepsView.StepLine]
    /// The topic's paragraph and example: the Inspector only (setup keeps one sentence).
    let explanation: Components.Schemas.TopicInfo?
    let onFix: ((String) -> Void)?
    /// Use <name> instead under a fit line (#5641); nil where no step can take it.
    var useSmaller: ((CandidateFit.Smaller) -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
                lineView(line)
            }
            if let explanation {
                TopicExplanation(topic: explanation, full: true)
            }
        }
        .padding(.vertical, 4)
    }

    @ViewBuilder
    private func lineView(_ line: RecipeStepsView.StepLine) -> some View {
        switch line {
        case .title(let text):
            Text(text).font(.headline)
        case .sentence(let text):
            Text(text).font(.body)
        case .place(let text, let cloud):
            Label(text, systemImage: cloud ? "cloud" : "desktopcomputer")
                .font(.callout)
                .foregroundStyle(.secondary)
        case .problem(let text):
            Label(text, systemImage: "exclamationmark.triangle")
                .font(.body)
                .foregroundStyle(.orange)
        case .fix(let title, let fix):
            Button(title) { onFix?(fix) }
                .controlSize(.small)
        case .runs(let text):
            Text(text).font(.callout).foregroundStyle(.secondary)
        case .detail(let text):
            // The rules' own reason, model ids included, belongs here and in the log only.
            Text(text).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
        case .fit(let fit):
            CandidateFitLabel(fit: fit, useSmaller: useSmaller)
        }
    }

    /// Where the step runs and the model by its card's name; nothing when the card has no name
    /// (an id is never shown in its place).
    static func whereItRuns(_ step: Components.Schemas.RecipeStep) -> String? {
        guard step.card != nil || step.runsOn != nil else { return nil }
        let place = step.usesCloud == true ? "In the cloud" : "On this Mac"
        guard let name = step.card?.note, !name.isEmpty else { return place }
        return "\(place) · \(name)"
    }

    /// The fix button's words, from the engine's `fix` (`StepProblem.fix`).
    static func fixTitle(_ fix: String) -> String {
        switch fix {
        case "download": "Download a model…"
        case "choose-cloud": "Use a cloud model…"
        case "allow-cloud": "Let pages leave this Mac"
        case "accept-licence": "Review the licence…"
        default: "Choose a model…"
        }
    }
}

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
