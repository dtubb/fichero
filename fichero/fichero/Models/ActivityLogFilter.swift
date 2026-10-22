import Foundation

/// The log's filter row (`activity.log.person-reads-like-a-copy-history`, `activity.log.problems-first`, #5960):
/// Problems (warnings and errors, the default when the log has any), All (the person's log), Everything (the
/// developer's raw log: debug lines, copyable). Pure, so the rules are checked without drawing the row.
enum ActivityLogFilter: String, CaseIterable, Identifiable {
    case problems = "Problems"
    case all = "All"
    case everything = "Everything"

    var id: String { rawValue }

    /// Everything adds the debug lines (`detail=developer`).
    var developer: Bool { self == .everything }

    /// Problems asks the engine for warnings and errors only (`level=problems`).
    var problemsOnly: Bool { self == .problems }

    /// The levels the engine counts as a problem (`_PROBLEM_LEVELS`).
    static let problemLevels: Set<String> = ["warning", "error", "critical"]

    /// "3 problems" for the closed Log disclosure; nil when there are none.
    static func problemCountWords(_ count: Int) -> String? {
        count > 0 ? "\(count) \(count == 1 ? "problem" : "problems")" : nil
    }

    static func hasProblems(_ lines: [ActivityJobLogLine]) -> Bool {
        lines.contains { problemLevels.contains($0.level) }
    }

    /// What shows: the person's choice on this row, else Everything if they chose it before (remembered), else the default.
    static func effective(chosen: ActivityLogFilter?, developer: Bool, hasProblems: Bool) -> ActivityLogFilter {
        chosen ?? (developer ? .everything : automatic(hasProblems: hasProblems))
    }

    /// What shows when the person has not chosen: Problems while the log has any, else All.
    static func automatic(hasProblems: Bool) -> ActivityLogFilter { hasProblems ? .problems : .all }
}

/// Whether the live log follows its newest line (`activity.window.open-a-run`): while the run is live, the Log is
/// open and the person has not scrolled up from the end. Pure, so the rule is checked without a scroll view.
enum ActivityLogFollow {
    static func shouldFollow(isLive: Bool, isOpen: Bool, atEnd: Bool) -> Bool { isLive && isOpen && atEnd }

    /// Scroll to the end of the page with the newest line (the log is the page's last section).
    static let endAnchor = "activity.log.end"
}
