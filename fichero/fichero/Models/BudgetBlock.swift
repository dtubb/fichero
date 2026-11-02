import FicheroAPIClient
import Foundation

/// The Budget block above Start (`designer.budget.beside-the-estimate`, #6295) read from the engine's `cloud_cap` line: the run cap
/// Start proposes (the best estimate, no margin), the step that costs most, and the step whose model the refusal offers to change.
/// Nothing is worked out here: every figure and every step is the engine's. Pure, for the tests.
struct BudgetBlock: Equatable {
    /// The run cap the engine proposes, in dollars; nil when the estimate is unknown or nothing.
    let proposedRunCapUsd: Double?
    /// The step (its workflow) that costs most, when the plan is over a cap.
    let dearestStep: String?
    /// The step whose model "Change the model" opens, from the engine's `fixes`.
    let changeModelStep: String?

    nonisolated init(_ line: Components.Schemas.CloudCapLine) {
        proposedRunCapUsd = line.proposedRunCapUsd
        dearestStep = line.dearestStep
        changeModelStep = line.fixes?.first { $0.kind == .changeModel }?.step
    }

    /// "This run, at most": the field's prompt, the proposal as the engine made it.
    nonisolated var prompt: String { proposedRunCapUsd.map { CloudCapFix.usd($0) } ?? "No limit" }

    /// A cap below 0 cannot be typed: the engine refuses it, so the field never holds one.
    nonisolated static func clamped(_ value: Double?) -> Double? { value.map { max($0, 0) } }

    /// The sentence beside the refusal naming the dearest step, in the person's words for that step (`title`).
    nonisolated func dearestWords(title: (String) -> String) -> String? {
        dearestStep.map { "\(title($0)) costs most: change its model to bring the run under the cap." }
    }
}
