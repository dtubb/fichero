import FicheroAPIClient
import SwiftUI

/// One chosen stage's page (sections 7c and 7d, #5668): what it does (the page's subtitle, the engine's sentence),
/// its example, the jobs it carries and who runs them, and its own questions with their defaults filled in
/// (`source.onboard.stages.page-says-what-it-does`, `.page-asks-its-questions`). The engine lists all of it; the page
/// lays it out. The models, the comparison on the sample pages and training join it as their slices land.
struct SetupStagePage: View {
    @Bindable var store: RecipeSetupStore
    let stage: Components.Schemas.SetupStage
    /// A step problem's fix (Ready's handler); the comparison of candidates; the project whose model finder opens.
    var onFix: ((String) -> Void)?
    var bakeoff: BakeoffSection.Context?
    var project: LibraryManager.LibraryReference?

    /// The stage's try on the samples, shared by the picture at the top and the samples below.
    @State private var tryStore: SetupStageTryStore?
    /// The stage's main step's candidates, for choosing who to compare.
    @State private var candidateFinder: ModelFinderStore?

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // What the stage does, played on the person's own sample page when it was tried, else on the example
            // (`source.onboard.stages.shows-what-it-does`); the candidates side by side when compared.
            StageShowcaseSection(stageId: stage.id, result: tryStore?.result, useThis: useThis)
                .environment(project?.storageService)
            if let sample = stage.exampleFromSamples, !sample.isEmpty {
                // An example from the person's own sample pages, once a try found one (Passages, #5805).
                Text("From your sample pages: \(sample)")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            } else if !stage.example.isEmpty {
                Text(stage.example)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let note = Self.howItAnswers(stage.id) {
                Text(note)
                    .font(.callout)
                    .fixedSize(horizontal: false, vertical: true)
            }
            whoRunsIt
            // This stage's steps left off until turned on: Read's Correct with no corrector here (#5677).
            RecipeLeftOffRows(store: store, onlyJobs: Set(stage.jobs))
            if !stage.questions.isEmpty {
                Divider()
                ForEach(stage.questions, id: \.key) { question in
                    SetupStageQuestionField(
                        question: question,
                        store: store,
                        answer: Binding(
                            get: { Self.answer(to: question, in: store.jobAnswers) },
                            set: { store.jobAnswers[question: question.key] = $0 }
                        )
                    )
                }
            }
            if stage.sampleable, let tryStore {
                Divider()
                if let who = StageCandidateChooser.whoDoes(stageId: stage.id) {
                    Text(who).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                }
                // Which of the step's candidates Compare on These Pages runs (up to three; none: the engine's own).
                if let finder = candidateFinder, !finder.candidates.isEmpty {
                    StageCandidateChooser(
                        candidates: finder.candidates,
                        chosen: Binding(get: { tryStore.chosenCandidates }, set: { tryStore.chosenCandidates = $0 }),
                        useSmaller: useSmaller
                    )
                }
                SetupStageSamples(store: tryStore, useThis: useThis)
                    .id(stage.id)
                    // The samples' thumbnails come from this project's storage (Organise's strip).
                    .environment(project?.storageService)
            }
        }
        // A try's result changes what an open question suggests (the kinds it found): ask the engine's list again.
        .onChange(of: tryStore?.result) { Task { await store.loadStages() } }
        // The plan's rows come from the recipe: propose it when this page needs it and there is none yet.
        .task(id: stage.id) {
            if tryStore?.stageId != stage.id {
                tryStore = stage.sampleable ? SetupStageTryStore(client: store.client, stageId: stage.id) : nil
            }
            if store.recipe == nil, store.canAssemble { await store.assemble() }
            // The training offers ride on the Start plan.
            if store.startPlan == nil { await store.loadStartPlan() }
            await loadCandidates()
        }
    }

    /// The stage's main step's candidates, from the per-step finder (its own store, so the project's finder keeps
    /// whatever it was showing).
    private func loadCandidates() async {
        guard stage.sampleable, let main = store.mainStep(forJobs: stage.jobs) else {
            candidateFinder = nil
            return
        }
        let finder = candidateFinder ?? ModelFinderStore(client: store.client)
        candidateFinder = finder
        await finder.load(store.finderQuery(job: main.job, step: main.id))
    }

    /// Use This under a compared candidate: that card for the stage's step (the use-candidate route).
    private var useThis: ((StageCandidate) -> Void)? {
        guard let step = store.stepId(forJobs: stage.jobs) else { return nil }
        let setup = store
        return { candidate in Task { await setup.useCard(candidate.card, named: candidate.title, forStep: step) } }
    }

    /// The main step's candidates the page read (`loadCandidates`), for its card's fit line (#5641); none for others.
    private func stepCandidates(_ stepId: String) -> [Components.Schemas.ModelCandidate] {
        guard let finder = candidateFinder, store.mainStep(forJobs: stage.jobs)?.id == stepId else { return [] }
        return finder.candidates
    }

    /// Use <name> instead (#5641): the smaller build of a model that won't fit, for the stage's main step, through the
    /// use-candidate route, as Use This does.
    private var useSmaller: ((CandidateFit.Smaller) -> Void)? {
        guard let main = store.mainStep(forJobs: stage.jobs) else { return nil }
        let setup = store
        return { smaller in Task { await setup.useCard(smaller.card, named: smaller.name, forStep: main.id) } }
    }

    /// Who runs it (`source.onboard.stages.page-who-runs-it`): this stage's own steps of the plan, with the model
    /// each would use, where it runs, Choose a model… and, for Read and Find Lines, the comparison of candidates.
    @ViewBuilder
    private var whoRunsIt: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Which model does it").font(.headline)
            if let recipe = store.recipe {
                RecipeStepsView(store: store, recipe: recipe, onFix: onFix, bakeoff: bakeoff, finder: project,
                                onlyJobs: Set(stage.jobs), candidatesOf: stepCandidates)
            } else {
                ForEach(stage.jobs, id: \.self) { job in
                    Label(store.jobs[job]?.name ?? job, systemImage: "circle").font(.callout)
                }
                Text("The model for each step is proposed once the material's languages and scripts are known.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    /// The answer a question shows: what the person gave, else what the engine has (this project's answer, else
    /// the default). Pure, for the tests.
    static func answer(to question: Components.Schemas.StageQuestion,
                       in answers: RecipeSetupAnswers.JobAnswers) -> StageAnswer? {
        if answers.isTyped(question.key) { return answers[question: question.key] }
        return answers.other[question.key]
            ?? StageAnswer.from(question.answer?.value) ?? StageAnswer.from(question._default?.value)
    }

    /// How a stage's results reach the project, where that is not plain (`finddocs.review.setup-page`): Organise
    /// applies only what it is sure enough of and leaves the rest for the person. The level is the project's, so
    /// it is not named here.
    static func howItAnswers(_ stageId: String) -> String? {
        switch stageId {
        case "organise":
            "A document it is sure enough of is applied by the run. Every other one is proposed: it waits in Items, "
                + "marked Proposed, for you to accept, reject or change which pages belong, and ⌘Z takes back any answer."
        default:
            nil
        }
    }
}

extension RecipeSetupAnswers.JobAnswers {
    /// Whether a question's key is one of the typed fields (always answered, by their defaults at least).
    func isTyped(_ key: String) -> Bool { CodingKeys(rawValue: key) != nil }
}

/// One stage question, by its kind: one choice, several, yes or no, or a line of text.
struct SetupStageQuestionField: View {
    let question: Components.Schemas.StageQuestion
    /// For a language question: the engine's language search (`GET /api/recipes/languages`).
    var store: RecipeSetupStore?
    @Binding var answer: StageAnswer?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(question.ask).font(.callout.weight(.medium))
            switch question.kind {
            case .one:
                Picker(question.ask, selection: Binding(
                    get: { if case .text(let id) = answer { id } else { "" } },
                    set: { answer = .text($0) }
                )) {
                    ForEach(question.options ?? [], id: \.id) { option in Text(option.title).tag(option.id) }
                }
                .labelsHidden()
            case .many where question.openEnded == true:
                // A question that names kinds: every kind, typed own kinds, chips from a sample try (#5805).
                StageKindsField(question: question, answer: $answer)
            case .many:
                FlowLayout(spacing: 6) {
                    ForEach(question.options ?? [], id: \.id) { option in
                        Toggle(option.title, isOn: Binding(
                            get: { if case .many(let ids) = answer { ids.contains(option.id) } else { false } },
                            set: { isOn in
                                var ids: [String] = if case .many(let current) = answer { current } else { [] }
                                if isOn { if !ids.contains(option.id) { ids.append(option.id) } } else { ids.removeAll { $0 == option.id } }
                                answer = .many(ids)
                            }
                        ))
                        .setupCheckbox()
                    }
                }
            case .yesNo:
                Toggle("Yes", isOn: Binding(
                    get: { if case .yesNo(let flag) = answer { flag } else { false } },
                    set: { answer = .yesNo($0) }
                ))
                .setupCheckbox()
            case .text:
                TextField(question.ask, text: Binding(
                    get: { if case .text(let text) = answer { text } else { "" } },
                    set: { answer = .text($0) }
                ))
                .textFieldStyle(.roundedBorder)
            case .language:
                // Any language, by the same search as the material's languages (Translate into, section 7d).
                if let store {
                    StageLanguageField(store: store, answer: $answer)
                }
            }
        }
    }
}

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

#Preview("A stage question of each kind") {
    @Previewable @State var answer: StageAnswer? = .many([])
    SetupStageQuestionField(
        question: Components.Schemas.StageQuestion(
            key: "entity_kinds", ask: "Which kinds of names?", kind: .many,
            readByAStep: true, openEnded: true, suggestions: ["people", "places"]
        ),
        answer: $answer
    )
    .padding()
    .frame(width: 420)
}
