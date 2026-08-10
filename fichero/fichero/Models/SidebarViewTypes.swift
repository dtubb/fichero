import Foundation

// MARK: - App View Mode

/// Which main view is active based on sidebar selection
enum AppViewMode: Equatable {
    case library(Document?)              // Library browsing - selected collection/folder
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
        case .chat, .comparison: return .chat
        case .workflow, .chain: return .workflow
        case .batches, .batch, .automation, .schedule, .trigger: return .workflow
        case .activity: return .workflow
        }
    }

    /// Identity-only log form. NEVER a payload dump: `String(describing:)`
    /// on a `.library(Document)` interpolated the document's ENTIRE
    /// pageContent — the user's archive, a whole book — into os_log
    /// (Daniel, 2026-08-10: "why is all that text in the log? … it's also
    /// about privacy"). os_log persists and travels in sysdiagnoses, so
    /// archive CONTENT must never reach it; and formatting megabytes on
    /// the main thread was itself a measured stall. Ids only.
    var logDescription: String {
        switch self {
        case .library(let doc): return "library(doc: \(doc?.id ?? "nil"))"
        case .chat: return "chat"
        case .comparison: return "comparison"
        case .workflow(let workflow): return "workflow(\(workflow?.id ?? "nil"))"
        case .chain: return "chain"
        case .batches: return "batches"
        case .batch: return "batch"
        case .automation: return "automation"
        case .schedule: return "schedule"
        case .trigger: return "trigger"
        case .activity: return "activity"
        }
    }
}

// MARK: - Activity Run Selection

/// Child type for activity run selection (Xcode Report Navigator style)
enum ActivityChildType: String, Equatable, CaseIterable {
    case console
    case progress
    case trace    // Run trace graph — what actually happened (#4320)
    case log      // Execution log

    var label: String {
        switch self {
        case .console: return "Console"
        case .progress: return "Progress"
        case .trace: return "Trace"
        case .log: return "Log"
        }
    }

    var icon: String {
        switch self {
        case .console: return "text.alignleft"
        case .progress: return "chart.bar.fill"
        case .trace: return "point.3.connected.trianglepath.dotted"
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
    var libraryId: UUID?
    var libraryName: String?
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
            libraryId: libraryId,
            libraryName: libraryName,
            childType: childType
        )
    }
}
