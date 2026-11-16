import FicheroAPIClient
import SwiftUI

/// Choose the Stages (sections 7c and 7d, #5668): the first decision about the work. The goals sit above as shortcuts
/// that tick the stages they need (`source.onboard.stages.goals-are-shortcuts`); every stage is a checkbox with its
/// explanation always showing (`source.onboard.stages.explanation-always-shown`); a stage another chosen stage needs
/// is ticked, fixed, with the engine's reason (`source.onboard.stages.needs-are-ticked`).
struct SetupStageChooser: View {
    @Bindable var store: RecipeSetupStore

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            goals
            Divider()
            if store.stages.isEmpty, let error = store.errorMessage {
                Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
            } else if store.stages.isEmpty {
                ProgressView()
            }
            ForEach(store.stages, id: \.id) { stage in
                SetupStageRow(
                    stage: stage,
                    isChosen: store.stageChoice?.chosen.contains(stage.id) ?? false,
                    neededBecause: store.stageChoice?.neededBecause(stage.id) ?? [],
                    toggle: { store.toggle(stage: stage.id) }
                )
            }
        }
        .task {
            await store.loadPurposes()
            await store.loadStages()
        }
    }

    /// The goals, as shortcuts: each ticks the stages it needs; unticking a stage afterwards is kept.
    private var goals: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Start from a goal").font(.headline)
            FlowLayout(spacing: 6) {
                ForEach(store.purposeOptions.filter { $0.id != "not-sure" && $0.parent == nil }, id: \.id) { goal in
                    Button(goal.title) { store.applyGoal(goal.id) }
                        .buttonStyle(.bordered)
                        .help(goal.description)
                }
            }
        }
    }
}

/// One stage in the chooser: its checkbox, its sentence and example always shown, and why it cannot be unticked.
struct SetupStageRow: View {
    let stage: Components.Schemas.SetupStage
    let isChosen: Bool
    let neededBecause: [String]
    let toggle: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Toggle(stage.title, isOn: Binding(get: { isChosen }, set: { _ in toggle() }))
                .setupCheckbox()
                .accessibilityIdentifier("setup.stage.row.\(stage.id)")
                .disabled(isChosen && !neededBecause.isEmpty)
            Text(stage.sentence)
                .font(.callout)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.leading, 20)
            if !stage.example.isEmpty {
                Text(stage.example)
                    .font(.caption)
                    .foregroundStyle(.tertiary)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.leading, 20)
            }
            ForEach(neededBecause, id: \.self) { why in
                Text(why).font(.caption).foregroundStyle(.secondary).padding(.leading, 20)
            }
        }
    }
}

#Preview("A stage, chosen and needed") {
    SetupStageRow(
        stage: Components.Schemas.SetupStage(
            id: "names", title: "Names", sentence: "Finds the people, places and things the pages name.",
            example: "“Juan de Mosquera, vecino de Popayán” gives a person and a place.",
            exampleCredit: Components.Schemas.ExampleCredit(
                title: "Sample page", shortCredit: "Sample", licence: "CC BY 4.0",
                sourceUrl: "https://example.org", licenceUrl: "https://creativecommons.org/licenses/by/4.0/"
            ),
            jobs: ["find-names-tag-words"], on: true, jobsInRecipe: [], questions: [],
            needs: [], sampleable: true, triedBy: .workflow
        ),
        isChosen: true,
        neededBecause: ["Dates & Times needs Names"],
        toggle: {}
    )
    .padding()
    .frame(width: 480)
}
