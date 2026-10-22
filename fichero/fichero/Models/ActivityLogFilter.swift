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
