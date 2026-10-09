import SwiftUI

// MARK: - Activity Run Model

/// Represents a workflow run (active or historical) for sidebar display
struct ActivityRun: Identifiable {
    /// Sidebar-unique identifier (scoped by library) used for SwiftUI list identity.
    let id: String
    /// Logical run identifier (thread ID) used for data loading and navigation.
    let runId: String
    let workflowId: String?
    let threadId: String?
    let workflowName: String  // Name of the workflow (for grouping)
    /// When the run started; `nil` when the engine's time could not be read,
    /// shown as unknown, never as now (#5432).
    let timestamp: Date?
    let status: ActivityRunStatus
    let progress: Double?
    let currentStep: String?
    let errorCount: Int
    let fileCount: Int  // Number of files processed (from metadata)
    let isLive: Bool  // True if from WorkflowExecutionObserver
    var libraryId: UUID?
    var libraryName: String?
    /// Why a failed run failed, as the runs table recorded it; the Activity
    /// table's state column shows it (`activity.window.row-shows-lane-state-reason`).
    var failureReason: String?

    /// The details' selection for this run (#5561): its job (the thread id)
    /// and its project. Nothing else is copied: the details read the row.
    var selection: ActivitySelection {
        ActivitySelection(jobId: runId, libraryId: libraryId)
    }
}

// MARK: - Run delete outcome (#4960)

/// What `ActivityStore.deleteRuns` actually did — names both halves rather
/// than a bare count, so a caller can say plainly "3 removed, 1 still
/// running" instead of a silent partial success.
struct RunDeleteOutcome: Equatable, Sendable {
    /// Run ids the engine actually removed (and `ActivityStore` has already
    /// spliced out of `runs`).
    let deletedIds: [String]
    /// Run ids that were requested (by id, or matched by a status filter)
    /// but NOT removed — most commonly a still-running run, which the
    /// engine never deletes out from under itself.
    let skippedIds: [String]
    /// Why the request failed, in words; nil when the engine answered. A
    /// failure is said, never read as "nothing to delete" (#5634).
    var failure: String?

    static let empty = RunDeleteOutcome(deletedIds: [], skippedIds: [])
}

/// What Clear Failed did in one project (`activity.window.clear-failed`,
/// #5634): failed runs deleted, failed jobs cleared, runs it could not
/// clear, and why a request failed.
struct ClearFailedOutcome: Equatable, Sendable {
    var runsCleared = 0
    var jobsCleared = 0
    var runsSkipped = 0
    var failures: [String] = []

    static func + (lhs: Self, rhs: Self) -> Self {
        Self(runsCleared: lhs.runsCleared + rhs.runsCleared, jobsCleared: lhs.jobsCleared + rhs.jobsCleared,
             runsSkipped: lhs.runsSkipped + rhs.runsSkipped, failures: lhs.failures + rhs.failures)
    }

    static func += (lhs: inout Self, rhs: Self) { lhs = lhs + rhs }

    /// The window's footer line: what was cleared, or that nothing was, and
    /// what could not be.
    var notice: String {
        var parts: [String] = []
        if runsCleared > 0 { parts.append("\(runsCleared) failed run\(runsCleared == 1 ? "" : "s")") }
        if jobsCleared > 0 { parts.append("\(jobsCleared) failed job\(jobsCleared == 1 ? "" : "s")") }
        var lines = [parts.isEmpty ? "No failed runs or jobs to clear." : "Cleared \(parts.joined(separator: " and "))."]
        if runsSkipped > 0 {
            lines.append("\(runsSkipped) run\(runsSkipped == 1 ? "" : "s") could not be cleared.")
        }
        if let failure = failures.first { lines.append("Couldn't clear everything: \(failure)") }
        return lines.joined(separator: " ")
    }
}

// MARK: - Activity Run Status

enum ActivityRunStatus {
    case running
    case paused
    case completed
    case failed
    case cancelled

    var icon: String {
        switch self {
        case .running: return "play.circle.fill"
        case .paused: return "pause.circle.fill"
        case .completed: return "checkmark.circle.fill"
        case .failed: return "xmark.circle.fill"
        case .cancelled: return "stop.circle.fill"
        }
    }

    var color: Color {
        switch self {
        case .running: return .blue
        case .paused: return .orange
        case .completed: return .green
        case .failed: return .red
        case .cancelled: return .orange
        }
    }

    /// The app-wide run vocabulary `RunControls` speaks (#4321).
    var workflowStatus: WorkflowStatus {
        switch self {
        case .running: return .running
        case .paused: return .paused
        case .completed: return .completed
        case .failed: return .failed
        case .cancelled: return .cancelled
        }
    }
}
