import Foundation

/// The four states of a stage page's output column (`wide.output.four-states`, #5668, #5806), worked out from the engine's try
/// result and never a guess: not tried, running, done, refused or failed. Never an empty column. Pure: no view, no network.
enum StepOutputState: Equatable {
    /// Nothing tried yet: the example, the sample strip and "Try on these N pages" with the engine's time and cost line.
    case notTried(line: String)
    /// Under way: progress in place, and Stop.
    case running(words: String)
    /// Finished. `stale`: it ran with earlier answers or another card, so it is shown dimmed and never as current
    /// (`wide.output.stale-says-so`).
    case done(stale: Bool)
    /// Refused or failed: the engine's sentence.
    case failed(words: String)

    /// The state from what the try store holds.
    static func of(_ input: StepOutputInputs) -> StepOutputState {
        if let refusal = input.refusal, !refusal.isEmpty { return .failed(words: refusal) }
        if let costQuestion = input.costQuestion, !costQuestion.isEmpty { return .notTried(line: costQuestion) }
        guard let result = input.result else {
            return input.isTrying ? .running(words: "Starting the try.")
                : .notTried(line: notTriedLine(pages: input.pages, estimate: input.estimate))
        }
        if result.isUnderWay { return .running(words: result.underWayWords ?? "Working on it.") }
        if let failure = result.failure { return .failed(words: failure) }
        return .done(stale: isStale(result, currentRevision: input.currentRevision))
    }

    /// "Try on these 5 pages, about 2 minutes, free on this Mac": the button's label and the engine's time and cost line.
    static func notTriedLine(pages: Int, estimate: String?) -> String {
        let count = pages == 1 ? "Try on this page" : "Try on these \(pages) pages"
        guard let estimate, !estimate.isEmpty else { return count }
        return "\(count), \(estimate)"
    }

    /// A result is stale when it says which answers it ran with and the stage has other answers now.
    static func isStale(_ result: SetupStageTryResult, currentRevision: String?) -> Bool {
        guard let ran = result.answersRevision, let now = currentRevision else { return false }
        return ran != now
    }

    /// The words over a stale result.
    static let staleWords = "Tried with the earlier answers; try again"
}

/// What the output column's state is worked out from. `currentRevision` is the stage listing's `answers_revision` now.
struct StepOutputInputs {
    let result: SetupStageTryResult?
    let refusal: String?
    let costQuestion: String?
    let isTrying: Bool
    let currentRevision: String?
    let pages: Int
    let estimate: String?
}
