import Foundation

// MARK: - Workflow Execution

/// Represents an active workflow execution
struct WorkflowExecution: Identifiable {
    let id: String  // workflow ID
    let name: String
    var threadId: String
    let startTime: Date
    var status: WorkflowStatus
    var nodeStates: [String: NodeExecutionState]  // keyed by node ID
    var documentProgress: [String: DocumentProgress]  // keyed by stable document/page identity
    var currentFilePath: String?
    var currentNodeId: String?
    var currentNodeName: String?
    var isRunning: Bool
    var workflowError: String?
    var totalFiles: Int = 0
    var processedFiles: Int = 0
    var processedFileIds: Set<String> = []
    var logLines: [String] = []  // Streamed execution log lines

    /// Ordered document progress for display
    var orderedDocumentProgress: [DocumentProgress] {
        Array(documentProgress.values).sorted { $0.documentName < $1.documentName }
    }

    /// Overall progress (0.0 to 1.0)
    var overallProgress: Double? {
        guard isRunning else { return nil }
        if totalFiles > 0 {
            return Double(processedFiles) / Double(totalFiles)
        }
        let states = nodeStates.values
        guard !states.isEmpty else { return 0 }
        let totalProgress = states.reduce(0.0) { $0 + $1.progress }
        return totalProgress / Double(states.count)
    }

    /// Current file name being processed
    var currentFileName: String? {
        guard let path = currentFilePath else { return nil }
        return (path as NSString).lastPathComponent
    }

    /// Running nodes
    var runningNodes: [NodeExecutionState] {
        nodeStates.values.filter { $0.status == .running || $0.status == .parallelRunning }
    }

    /// Completed nodes count
    var completedNodesCount: Int {
        nodeStates.values.filter { $0.status == .completed }.count
    }
}
