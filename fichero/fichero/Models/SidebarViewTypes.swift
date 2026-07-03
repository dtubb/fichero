import Foundation

// MARK: - App View Mode

/// Which main view is active based on sidebar selection
enum AppViewMode: Equatable {
    case library(Document?)              // Library browsing - selected collection/folder
    case search(SavedSearch?)            // Search view - selected saved search or new search
    case chat(Conversation?)             // Chat view - RAG conversation with documents
    case comparison(ComparisonSummary?)  // Model comparison view
    case workflow(WorkflowSidebarItem?)  // Workflow editor - selected workflow
    case chain(WorkflowChain?)           // Chain editor - workflow chain
    case batches                         // Batch jobs list and management
    case batch(BatchInfo?)               // Batch detail view
    case automation                      // Schedules and file triggers
    case schedule(ScheduleInfo?)         // Schedule detail/creation view
    case trigger(TriggerInfo?)           // Trigger detail/creation view
    case activity(SelectedActivityRun?)  // All workflow runs - optional selected run for detail view

    var category: ItemCategory {
        switch self {
        case .library: return .folder
        case .search: return .search
        case .chat, .comparison: return .chat
        case .workflow, .chain: return .workflow
        case .batches, .batch, .automation, .schedule, .trigger: return .workflow
        case .activity: return .workflow
        }
    }
}

// MARK: - Activity Run Selection

/// Child type for activity run selection (Xcode Report Navigator style)
enum ActivityChildType: String, Equatable, CaseIterable {
    case console
    case progress
    case log      // Execution log

    var label: String {
        switch self {
        case .console: return "Console"
        case .progress: return "Progress"
        case .log: return "Log"
        }
    }

    var icon: String {
        switch self {
        case .console: return "text.alignleft"
        case .progress: return "chart.bar.fill"
        case .log: return "doc.text"
        }
    }
}

/// Selected activity run for the detail view
/// Lightweight reference - full details loaded on demand
struct SelectedActivityRun: Equatable, Identifiable, Hashable {
    let id: String
    let name: String
    let workflowId: String?
    let threadId: String?
    let timestamp: Date
    let status: ActivityRunStatusType
    let isLive: Bool  // True if currently running (use observer for updates)
    var childType: ActivityChildType?  // Which child is selected (nil = overview)

    enum ActivityRunStatusType: String, Equatable {
        case running
        case paused
        case completed
        case failed
        case cancelled
    }

    /// Create a copy with a different child type
    func with(childType: ActivityChildType?) -> SelectedActivityRun {
        SelectedActivityRun(
            id: id,
            name: name,
            workflowId: workflowId,
            threadId: threadId,
            timestamp: timestamp,
            status: status,
            isLive: isLive,
            childType: childType
        )
    }
}
