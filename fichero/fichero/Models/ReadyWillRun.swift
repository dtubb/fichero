import FicheroAPIClient
import Foundation

/// What Ready shows (`wide.ready.only-what-will-run`, #5840, #6295): the steps that will run, in run order, each with its pages;
/// the estimate; the skipped steps, each with why and its fix; and Start with its reason. Nothing else: the offered jobs, the
/// left-off rows and the taken-out rows are on their stage pages, so this model does not hold them at all (a step is added on its
/// stage's page, `wide.ready.adding-a-step-is-on-its-stage-page`). Pure.
struct ReadyWillRun: Equatable {
    struct Line: Equatable, Identifiable {
        let id: String
        let job: String
        let steps: [String]
        let runsOn: String
        /// "done on 4 of 92" when the last run did some of it, else nil.
        let progress: String?
    }

    struct Skipped: Equatable, Identifiable {
        let id: String
        let why: String
        let fix: String?
    }

    let running: [Line]
    let skipped: [Skipped]
    let pages: Int
    let totalCostUsd: Double?
    /// Why Start waits, in words; nil when it can be pressed.
    let startReason: String?

    init(plan: Components.Schemas.StartPlan, startReason: String?) {
        running = plan.runs.enumerated().map { index, run in
            Line(id: "\(index):\(run.steps.joined(separator: ","))", job: run.job, steps: run.steps, runsOn: run.runsOn,
                 progress: run.done.flatMap { done in run.of.map { "done on \(done) of \($0)" } })
        }
        skipped = plan.skipped.map { Skipped(id: $0.step, why: $0.why, fix: $0.fix) }
        pages = plan.estimate.pages
        totalCostUsd = plan.estimate.totalCostUsd
        self.startReason = startReason
    }

    /// The step ids that will run, in order: what Ready's boxes are made of.
    var stepIds: [String] { running.flatMap(\.steps) }
}
