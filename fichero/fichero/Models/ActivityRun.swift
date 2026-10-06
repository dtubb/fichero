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

    static let empty = RunDeleteOutcome(deletedIds: [], skippedIds: [])
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
