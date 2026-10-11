import FicheroAPIClient
import SwiftUI

/// One chosen stage's page (sections 7c and 7d, #5668): what it does (the page's subtitle, the engine's sentence),
/// its example, the jobs it carries and who runs them, and its own questions with their defaults filled in
/// (`source.onboard.stages.page-says-what-it-does`, `.page-asks-its-questions`). The engine lists all of it; the page
/// lays it out. The models, the comparison on the sample pages and training join it as their slices land.
struct SetupStagePage: View {
    @Bindable var store: RecipeSetupStore
    let stage: Components.Schemas.SetupStage

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            if !stage.example.isEmpty {
                Text(stage.example)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            jobs
            if !stage.questions.isEmpty {
                Divider()
                ForEach(stage.questions, id: \.key) { question in
                    SetupStageQuestionField(
                        question: question,
                        answer: Binding(
                            get: { Self.answer(to: question, in: store.jobAnswers) },
                            set: { store.jobAnswers[question: question.key] = $0 }
                        )
                    )
                }
            }
        }
    }

    /// The jobs this stage carries, in step order, each in the registry's words.
    private var jobs: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("What it runs").font(.headline)
            ForEach(stage.jobs, id: \.self) { job in
                Label(store.jobs[job]?.name ?? job, systemImage: stage.jobsInRecipe.contains(job) ? "checkmark.circle" : "circle")
                    .font(.callout)
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
            }
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
