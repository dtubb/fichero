import Foundation

// MARK: - Execution State Models

struct WorkflowExecutionState {
    var status: WorkflowStatus
    var documentProgress: [DocumentProgress]
    var error: String?
}

enum WorkflowStatus {
    case idle
    case running
    case paused
    case completed
    case failed
    /// User-initiated stop (#4321). Distinct from `.failed` — a cancelled run
    /// used to render as Failed everywhere because the case didn't exist, and
    /// every mapper collapsed the backend's "cancelled" onto `.failed`.
    case cancelled
}

struct DocumentProgress: Identifiable {
    let id: String
    let documentName: String
    var stepStatuses: [String: StepStatus]
}

enum StepStatus {
    case pending
    case running
    case completed(duration: Double?, cached: Bool)
    case failed(error: String?)
}

// MARK: - Mock Execution State

extension WorkflowExecutionState {
    static let sample = WorkflowExecutionState(
        status: .running,
        documentProgress: [
            DocumentProgress(
                id: "doc-1",
                documentName: "letter_001.jpg",
                stepStatuses: [
                    "step-1": .completed(duration: 2.3, cached: false),
                    "step-2": .running,
                    "step-3": .pending
                ]
            ),
            DocumentProgress(
                id: "doc-2",
                documentName: "letter_002.jpg",
                stepStatuses: [
                    "step-1": .completed(duration: 1.8, cached: false),
                    "step-2": .pending,
                    "step-3": .pending
                ]
            ),
            DocumentProgress(
                id: "doc-3",
                documentName: "letter_003.jpg",
                stepStatuses: [
                    "step-1": .pending,
                    "step-2": .pending,
                    "step-3": .pending
                ]
            )
        ]
    )
}
