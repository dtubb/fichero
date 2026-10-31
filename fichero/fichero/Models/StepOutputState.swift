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

    /// The state from what the try store holds. `currentRevision` is the stage listing's `answers_revision` now.
    static func of(result: SetupStageTryResult?, refusal: String?, costQuestion: String?, isTrying: Bool,
                   currentRevision: String?, pages: Int, estimate: String?) -> StepOutputState {
        if let refusal, !refusal.isEmpty { return .failed(words: refusal) }
        if let costQuestion, !costQuestion.isEmpty { return .notTried(line: costQuestion) }
        guard let result else {
            return isTrying ? .running(words: "Starting the try.") : .notTried(line: notTriedLine(pages: pages, estimate: estimate))
        }
        if result.isUnderWay { return .running(words: result.underWayWords ?? "Working on it.") }
        if let failure = result.failure { return .failed(words: failure) }
        return .done(stale: isStale(result, currentRevision: currentRevision))
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
