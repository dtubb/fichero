import Foundation
import Observation

/// Which failures the Activity popover may still show (#5666, Daniel 2026-10-11): only recent ones, those from the
/// last hour or since the person last opened the popover, whichever is shorter. Older ones stay in the Activity
/// window. Pure, so the rule is tested without a clock.
struct ActivityErrorWindow: Equatable {
    /// The failures that were there when the popover was last closed: seen, so not shown again.
    var seen: Set<String> = []
    /// When this app first saw each failure.
    var firstSeen: [String: Date] = [:]
    var now = Date()

    static let hour: TimeInterval = 60 * 60

    /// Whether a failure is recent: not seen at the last opening, and first seen within the hour.
    func isRecent(_ jobId: String) -> Bool {
        guard !seen.contains(jobId) else { return false }
        guard let first = firstSeen[jobId] else { return true }
        return now.timeIntervalSince(first) <= Self.hour
    }
}

/// The app's record of the failures it has seen and the ones the person has seen in the popover. The engine's job
/// list carries no time for a failure, so the first time this app saw it stands in for when it failed; the failures
/// seen in the popover are kept across launches, so an old one never comes back.
@MainActor
@Observable
final class ActivityErrorLedger {
    static let shared = ActivityErrorLedger()

    private(set) var firstSeen: [String: Date] = [:]
    private let defaults: UserDefaults
    private static let seenKey = "activity.popover.seenFailures"

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
    }

    /// The failures seen when the popover was last closed.
    var seen: Set<String> { Set(defaults.stringArray(forKey: Self.seenKey) ?? []) }

    /// Note the failures listed now; a new one is stamped with now.
    func note(failedIds: [String], now: Date = Date()) {
        for id in failedIds where firstSeen[id] == nil { firstSeen[id] = now }
    }

    /// The window the popover shows its errors through, as it opens.
    func window(now: Date = Date()) -> ActivityErrorWindow {
        ActivityErrorWindow(seen: seen, firstSeen: firstSeen, now: now)
    }

    /// The popover closed: the failures it could show are seen. Only the listed ones are kept, so the record does
    /// not grow without end.
    func markSeen(_ failedIds: [String]) {
        defaults.set(Array(Set(failedIds)), forKey: Self.seenKey)
    }
}
