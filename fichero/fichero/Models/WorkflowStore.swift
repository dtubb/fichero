import FicheroAPIClient
import Foundation
import Observation
import OSLog

// Store for managing workflows with backend persistence
@MainActor
@Observable
final class WorkflowStore: ChangeEventConsumer {
    var workflows: [WorkflowSidebarItem] = []
    var directlyRunnableWorkflows: [WorkflowSidebarItem] {
        workflows.filter(\.canRunDirectly)
    }
    var selectedWorkflow: WorkflowSidebarItem?
    var isLoading = false
    var isSaving = false
    var isConnected = false
    var error: Error?

    /// Cached backend tool metadata, keyed by lowercased tool name. Populated
    /// by `loadWorkflows()` so the canvas's `WorkflowNodeView` can render the
    /// correct icon/color for any registered tool — palette and graph share
    /// one source of truth (#725). Empty until first successful load; views
    /// fall back to a hardcoded dictionary for unknown tools.
    var toolRegistry: [String: ToolInfo] = [:]

    /// Bumped when a `workflow.*` change event arrives so interested views can
    /// invalidate their cached workflow-dependent UI.
    var changeToken: Int = 0

    let logger = Logger(subsystem: "app.fichero.fichero", category: "WorkflowStore")
    let workflowService: WorkflowService
    let ficheroClient: FicheroClient
    // Empty: backend ships the canonical default workflows (Transcribe,
    // Catalogue, Catalogue (composable)) via JSON in
    // fichero-server/.../resources/default_workflows. The Swift-side
    // `Default · Transcribe Files` / `Default · Transcribe Collection`
    // duplicated backend's Transcribe — removed in #722.
    // Note: there used to be a Swift-defined `defaultWorkflowTemplates`
    // array of `DefaultWorkflowTemplate` here. Defaults now live in the
    // backend's JSON files and are re-seeded by `reinstallDefaults` on
    // every session start. Removed in #722 to stop creating duplicates.

    // @ObservationIgnored: a lazily-built transport, not observable UI state.
    // @Observable would otherwise try to wrap this `lazy var` in an init
    // accessor, which is illegal on a computed/lazy property.
    @ObservationIgnored
    lazy var executionService: WorkflowExecutionService = {
        WorkflowExecutionService(ficheroClient: ficheroClient)
    }()

    init(ficheroClient: FicheroClient) {
        self.ficheroClient = ficheroClient
        self.workflowService = WorkflowService(ficheroClient: ficheroClient)
    }

    // MARK: - ChangeEventConsumer

    nonisolated var changeDomains: Set<String> { ["workflow"] }

    func apply(_ event: ChangeEvent) {
        changeToken &+= 1
    }

    func resync() async {
        await loadWorkflows()
    }
}

// MARK: - Error Types

enum WorkflowStoreError: Error, LocalizedError {
    case notFound(String)
    case saveFailed(String)
    case executionFailed(String)
    case templateInstallFailed(String)

    var errorDescription: String? {
        switch self {
        case .notFound(let message):
            return "Not found: \(message)"
        case .saveFailed(let message):
            return "Save failed: \(message)"
        case .executionFailed(let message):
            return "Execution failed: \(message)"
        case .templateInstallFailed(let message):
            return "Template install failed: \(message)"
        }
    }
}

// Removed: `DefaultWorkflowTemplate` enum (Transcribe Files / Transcribe Collection)
// — replaced by backend-shipped JSON workflows. See #722.
