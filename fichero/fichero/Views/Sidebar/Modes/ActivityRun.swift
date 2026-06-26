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
    let timestamp: Date
    let status: ActivityRunStatus
    let progress: Double?
    let currentStep: String?
    let errorCount: Int
    let fileCount: Int  // Number of files processed (from metadata)
    let isLive: Bool  // True if from WorkflowExecutionObserver

    /// Convert to SelectedActivityRun for viewMode
    func toSelectedRun() -> SelectedActivityRun {
        SelectedActivityRun(
            id: runId,
            name: workflowName,
            workflowId: workflowId,
            threadId: threadId,
            timestamp: timestamp,
            status: status.toStatusType(),
            isLive: isLive,
            childType: nil
        )
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

    func toStatusType() -> SelectedActivityRun.ActivityRunStatusType {
        switch self {
        case .running: return .running
        case .paused: return .paused
        case .completed: return .completed
        case .failed: return .failed
        case .cancelled: return .cancelled
        }
    }
}
