import Foundation
import Observation

/// The workflow bar's run state, in ONE reference (`ViewValueSizeTests`: thirteen inline `@State` values made `ContentView` 6208 bytes, past its
/// 6064 ceiling; the test file's own rule is to box, not raise). `ContentView` keeps each name as a computed property that forwards here,
/// so no caller changes; `@Observable` keeps the views that read a value updating when it changes.
@MainActor
@Observable
final class WorkflowBarRunState {
    var isRunningStagedChain: Bool = false
    var workflowBarChainId: String?
    var workflowBarChainRestoreAttempted: Bool = false
    var lastChainRunTargets: [String] = []
    var runningStagedStepIndex: Int?
    var stagedChainRunTask: Task<Void, Never>?
    var workflowRunRegistry: WorkflowRunRegistry = WorkflowRunRegistry()
    var detachedRunTasks: [UUID: Task<Void, Never>] = [:]
    var barChainDetached: Bool = false
    var attachedRunRegistryId: UUID?
    var workflowScopeOverride: WorkflowBarPolicy.RunScope?
    var stagedChainCost: StagedChainCost?
    var stagedChainActualCost: StagedChainCost?
}
