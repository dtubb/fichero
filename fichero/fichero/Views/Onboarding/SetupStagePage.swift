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

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            if !stage.example.isEmpty {
                Text(stage.example)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            whoRunsIt
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
            // Train or fine-tune a model of the project's own for this stage's steps (Kraken, spaCy, Core ML, MLX
            // LoRA), where the engine offers it (`source.onboard.stages.page-trains`); offered, never run at Start.
            if !store.trainOffers(forJobs: Set(stage.jobs)).isEmpty {
                Divider()
                Text("Train your own").font(.headline)
                RecipeTrainOffersFields(store: store, onlyJobs: Set(stage.jobs))
            }
            if stage.sampleable {
                Divider()
                SetupStageSamples(store: SetupStageTryStore(client: store.client, stageId: stage.id))
                    .id(stage.id)
            }
        }
        // The plan's rows come from the recipe: propose it when this page needs it and there is none yet.
        .task(id: stage.id) {
            if store.recipe == nil, store.canAssemble { await store.assemble() }
            // The training offers ride on the Start plan.
            if store.startPlan == nil { await store.loadStartPlan() }
        }
    }

    /// Who runs it (`source.onboard.stages.page-who-runs-it`): this stage's own steps of the plan, with the model
    /// each would use, where it runs, Choose a model… and, for Read and Find Lines, the comparison of candidates.
    @ViewBuilder
    private var whoRunsIt: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Who runs it").font(.headline)
            if let recipe = store.recipe {
                RecipeStepsView(store: store, recipe: recipe, onFix: onFix, bakeoff: bakeoff, finder: project,
                                onlyJobs: Set(stage.jobs))
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
    @Previewable @State var answer: StageAnswer? = .many(["people"])
    SetupStageQuestionField(
        question: Components.Schemas.StageQuestion(
            key: "entity_kinds", ask: "Which kinds of names?", kind: .many,
            options: [.init(id: "people", title: "People"), .init(id: "places", title: "Places")],
            readByAStep: true
        ),
        answer: $answer
    )
    .padding()
    .frame(width: 420)
}
