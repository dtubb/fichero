import Foundation
import Observation

/// Which failures the Activity popover may still show (#5666, Daniel 2026-10-11): only recent ones, those from the
/// last hour or since the person last opened the popover, whichever is shorter. Older ones stay in the Activity
/// window. Pure, so the rule is tested without a clock.
struct ActivityErrorWindow: Equatable {
    /// The failures that were there when the popover was last closed, by `seenKey`: seen, so not shown again.
    var seen: Set<String> = []
    /// When each failure failed: the engine's `failed_at`, else when this app first saw it.
    var firstSeen: [String: Date] = [:]
    /// The engine's `failed_at` of each failure that has one.
    var failedAt: [String: Date] = [:]
    var now = Date()

    static let hour: TimeInterval = 60 * 60

    /// A failure's key in the seen record: its job and when it failed, so the same job failing again after a retry
    /// is a new failure and shows again. A failure without `failed_at` is keyed by its job alone.
    static func seenKey(_ jobId: String, failedAt: Date?) -> String {
        guard let failedAt else { return jobId }
        return "\(jobId)@\(failedAt.ISO8601Format())"
    }

    /// Whether a failure is recent: not seen at the last opening, and failed within the hour.
    func isRecent(_ jobId: String) -> Bool {
        guard !seen.contains(Self.seenKey(jobId, failedAt: failedAt[jobId])) else { return false }
        guard let first = firstSeen[jobId] else { return true }
        return now.timeIntervalSince(first) <= Self.hour
    }
}

/// The app's record of the failures it has seen and the ones the person has seen in the popover. When a failure
/// failed is the engine's `failed_at`; only a failure listed without one (an engine from before it) is stamped with
/// the first time this app saw it. The failures seen in the popover are kept across launches, so an old one never
/// comes back.
@MainActor
@Observable
final class ActivityErrorLedger {
    static let shared = ActivityErrorLedger()

    private(set) var firstSeen: [String: Date] = [:]
    private(set) var failedAt: [String: Date] = [:]
    private let defaults: UserDefaults
    private static let seenDefaultsKey = "activity.popover.seenFailures"

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
    }

    /// The failures seen when the popover was last closed.
    var seen: Set<String> { Set(defaults.stringArray(forKey: Self.seenDefaultsKey) ?? []) }

    /// Note the failures listed now: each at the engine's `failed_at`; one without it, at the first time it was seen.
    func note(failed jobs: [ActivityJob], now: Date = Date()) {
        for job in jobs {
            if let failed = job.failedAt {
                if firstSeen[job.id] != failed { firstSeen[job.id] = failed }
                if failedAt[job.id] != failed { failedAt[job.id] = failed }
            } else if firstSeen[job.id] == nil {
                firstSeen[job.id] = now
            }
        }
    }

    /// The window the popover shows its errors through, as it opens.
    func window(now: Date = Date()) -> ActivityErrorWindow {
        ActivityErrorWindow(seen: seen, firstSeen: firstSeen, failedAt: failedAt, now: now)
    }

    /// The popover closed: the failures it could show are seen, each by its job and when it failed. Only the
    /// listed ones are kept, so the record does not grow without end.
    func markSeen(_ failed: [ActivityJob]) {
        let keys = failed.map { ActivityErrorWindow.seenKey($0.id, failedAt: $0.failedAt) }
        defaults.set(Array(Set(keys)), forKey: Self.seenDefaultsKey)
    }
}
