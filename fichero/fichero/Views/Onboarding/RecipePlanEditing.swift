import FicheroAPIClient
import SwiftUI

// Ready: the plan can be edited (#5627, `source.onboard.plan-editable`). A step can be taken out, unless a later
// step needs what it gives (the engine says which, in `needed_by`); what was taken out is listed with Put Back.
// The edit is an answer (`answers.removed_jobs`), so the engine leaves the step out of every plan it proposes,
// Ready saves that plan, and Start runs it. Changing a step's model is the model finder's (Find a Reader…,
// `RecipeSetupStore.useCandidate(_:forStep:)`): it sits beside these controls, never in them.

extension RecipeStepsView {
    /// Under a step's row on Ready: Remove from Plan, or why it cannot go.
    @ViewBuilder
    func planEditControls(for step: Components.Schemas.RecipeStep) -> some View {
        if RecipeSetupStore.canTakeOut(step) {
            Button("Remove from Plan") { Task { await store.takeOut(job: step.job) } }
                .controlSize(.small)
                .disabled(store.isAssembling)
                .help("Leave this step out; Start runs the plan without it. You can put it back.")
        } else {
            Text(Self.neededSentence(step, store: store))
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// "Read each line needs it, so it stays." from the engine's `needed_by`.
    static func neededSentence(_ step: Components.Schemas.RecipeStep, store: RecipeSetupStore) -> String {
        let names = (step.neededBy ?? []).map { store.title(ofStepId: $0) }
        let joined = names.count > 1 ? names.dropLast().joined(separator: ", ") + " and " + (names.last ?? "")
            : names.first ?? ""
        return "\(joined) \(names.count > 1 ? "need" : "needs") it, so it stays."
    }
}

/// The steps taken out of the plan, each with Put Back (#5627).
struct RecipeTakenOutRows: View {
    let store: RecipeSetupStore
    let removed: [Components.Schemas.TakenOutStep]

    var body: some View {
        if !removed.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                Text("Taken out of the plan").font(.subheadline.weight(.semibold))
                ForEach(removed, id: \.job) { step in
                    HStack(alignment: .firstTextBaseline) {
                        Text(step.title).font(.callout).foregroundStyle(.secondary)
                        Spacer()
                        Button("Put Back") { Task { await store.putBack(job: step.job) } }
                            .controlSize(.small)
                            .disabled(store.isAssembling)
                    }
                }
            }
        }
    }
}

/// The steps left off until turned on (#5677), one line each with what turning it on would cost, and Turn On. On
/// Set Up's Read page (that stage's) and in the Start section (all of them).
struct RecipeLeftOffRows: View {
    let store: RecipeSetupStore
    /// A stage's jobs; nil lists every left-off step.
    var onlyJobs: Set<String>?

    var body: some View {
        let steps = store.leftOff(forJobs: onlyJobs)
        if !steps.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                ForEach(steps, id: \.job) { step in
                    HStack(alignment: .firstTextBaseline) {
                        Text(step.sentence)
                            .font(.callout)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                        Spacer()
                        Button("Turn On") { Task { await store.turnOn(job: step.job) } }
                            .controlSize(.small)
                            .disabled(store.isAssembling)
                            .help("Add \(step.title) to the plan; Start then says what it needs")
                    }
                }
            }
        }
    }
}

#Preview("Taken out of the plan") {
    RecipeTakenOutRows(store: RecipeSetupStore(client: FicheroClient(libraryPath: nil)),
                       removed: [.init(job: "translate", title: "Translate"),
                                 .init(job: "find-statements", title: "Find statements")])
        .padding()
        .frame(width: 520)
}
