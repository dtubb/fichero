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


//  Below: moved here from WorkflowExecutionService.swift for file_length (#5113),
//  byte-for-byte. They belong beside WorkflowExecution above — the service moves these
//  shapes, it does not own them.

struct ExecutionThread: Identifiable, Hashable {
    let threadId: String
    let workflowId: String
    let workflowName: String
    let status: ExecutionStatus
    let checkpointId: String?
    let error: String?

    var id: String { threadId }
}

extension ExecutionThread: Codable {
    enum CodingKeys: String, CodingKey {
        case threadId = "thread_id"
        case workflowId = "workflow_id"
        case workflowName = "workflow_name"
        case status
        case checkpointId = "checkpoint_id"
        case error
    }
}

/// Workflow execution status
enum ExecutionStatus: String, Codable {
    case running
    case paused
    case completed
    case error
    case failed
    case cancelled
    case stopped
    case deleted

    /// Whether the persisted run has stopped for good (#4457).
    ///
    /// `running` and `paused` are the two states a run can still leave on its
    /// own — a paused run resumes and streams again — so everything else is
    /// terminal. That is deliberately the SAME split
    /// `WorkflowExecutionStore.shouldSubscribe(status:)` makes on
    /// `WorkflowStatus`; the two enums are separate, but "can this run still
    /// move?" must not get two different answers. Anything that needs the
    /// split should read it from here rather than re-listing the cases.
    var isTerminal: Bool {
        switch self {
        case .running, .paused:
            return false
        case .completed, .error, .failed, .cancelled, .stopped, .deleted:
            return true
        }
    }
}

// The thread-list response is now the generated `Components.Schemas.ThreadListResponse`
// (mapped in `listThreads`); the hand-written struct was retired in #1712.

// Note: AnyCodable is defined in Document.swift

// MARK: - Errors

enum WorkflowExecutionError: LocalizedError, Equatable {
    case invalidResponse
    case serverError(Int, String)
    /// The engine answered a pause/cancel with a `status` this build does not
    /// know (#4402). Loud on purpose — see `controlOutcome(fromRawStatus:)`.
    case unrecognizedControlStatus(String)

    var errorDescription: String? {
        switch self {
        case .invalidResponse:
            return "Invalid response from server"
        case let .serverError(code, message):
            return "Server error (\(code)): \(message)"
        case let .unrecognizedControlStatus(raw):
            return "The engine answered with an unrecognized run status: '\(raw)'"
        }
    }
}

// MARK: - Run-control outcome (#4402)

/// What a pause/cancel POST actually reported.
///
/// The engine answers these politely — a run it has never heard of comes back
/// **200** with `status="not_running"`, not 404. Until #4402 the Swift side
/// decoded that body and discarded it, which is why Stop and Pause looked dead:
/// the one signal that said "there is nothing here to stop" was the one signal
/// nobody read.
enum RunControlOutcome: Equatable, Sendable {
    /// The engine accepted the request and will act on it asynchronously
    /// (`pause_requested` / `cancel_requested`). The run's own stream or a
    /// status refresh carries the transition.
    case requested

    /// The engine settled the run there and then and reported its new
    /// lifecycle status. No poll needed — this IS the authoritative answer.
    case settled(WorkflowStatus)

    /// The run had already finished before the request arrived. The row is
    /// real, so its true terminal state is worth fetching.
    case alreadyTerminal

    /// **The engine has no such run.** Typically a row left behind by a killed
    /// engine: the database still says `running`, the process that would have
    /// answered for it is gone, and no event will ever settle it. Polling its
    /// status returns `running` forever, which is precisely how a row spins
    /// after its workflow has stopped (#4346). The client must settle it.
    case notRunning
}
