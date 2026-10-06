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
    // `.batch(BatchInfo?)` DELETED (#4705 increment 4a): a placeholder case
    // that always rendered "Batch monitoring is unified under Activity" —
    // restore already redirected the persisted string to `.activity(nil)`
    // (`ContentView+Persistence.swift`), and the one construction site
    // (`SidebarView+SelectionHandling.swift`) now constructs `.activity(nil)`
    // directly instead.
    case automation                      // Schedules and file triggers
    case schedule(ScheduleInfo?)         // Schedule detail/creation view
    case trigger(TriggerInfo?)           // Trigger detail/creation view
    case activity(ActivitySelection?)   // Activity - the selected row, shown in the details view (#5561)

    var category: ItemCategory {
        switch self {
        case .library: return .folder
        case .chat, .comparison: return .chat
        case .workflow, .chain: return .workflow
        case .batches, .automation, .schedule, .trigger: return .workflow
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
        case .automation: return "automation"
        case .schedule: return "schedule"
        case .trigger: return "trigger"
        case .activity: return "activity"
        }
    }
}

// MARK: - Activity selection (#5561)

/// The Activity details' selection: one row's job id and the project it is in
/// (`activity.details.one-mount`). The details view reads that row's node of
/// the job tree from the project's `ActivityStore` (the record the table
/// reads), so nothing about the row is copied here: a snapshot frozen at the
/// click is what made the old details view stale (#5561).
struct ActivitySelection: Hashable, Identifiable {
    /// The row's job: a run's thread id, a step's `<run>:<step>`, a page's job
    /// id, or a job of its own.
    let jobId: String
    var libraryId: UUID?

    var id: String { "\(libraryId?.uuidString ?? "")|\(jobId)" }
}
