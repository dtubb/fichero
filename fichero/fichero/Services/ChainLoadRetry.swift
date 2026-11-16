/// When a chains load that was cancelled is asked again (`models.chains.load-retries-a-cancelled-request`, #6479).
enum ChainLoadRetry {
    static let attempts = 3

    /// Seconds to wait before asking again, or nil to stop: only a request the engine's first-launch adoption
    /// cancelled is retried (never a cancelled task, never another error), at most `attempts` times.
    static func wait(afterAttempt attempt: Int, requestCancelled: Bool, taskCancelled: Bool) -> Double? {
        guard requestCancelled, !taskCancelled, attempt <= attempts else { return nil }
        return 0.5 * Double(attempt)
    }
}
