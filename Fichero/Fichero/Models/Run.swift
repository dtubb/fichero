import Foundation

// MARK: - Run Status

/// Workflow run status enum matching Python RunStatus
enum RunStatus: String, Codable, CaseIterable {
    case queued
    case running
    case completed
    case failed
    case cancelled

    var displayName: String {
        switch self {
        case .queued: return "Queued"
        case .running: return "Running"
        case .completed: return "Completed"
        case .failed: return "Failed"
        case .cancelled: return "Cancelled"
        }
    }

    var icon: String {
        switch self {
        case .queued: return "clock"
        case .running: return "arrow.triangle.2.circlepath"
        case .completed: return "checkmark.circle"
        case .failed: return "exclamationmark.triangle"
        case .cancelled: return "xmark.circle"
        }
    }

    var color: String {
        switch self {
        case .queued: return "gray"
        case .running: return "blue"
        case .completed: return "green"
        case .failed: return "red"
        case .cancelled: return "orange"
        }
    }

    var isTerminal: Bool {
        switch self {
        case .completed, .failed, .cancelled:
            return true
        case .queued, .running:
            return false
        }
    }
}

// MARK: - Run Model

/// An execution of a workflow on documents.
/// Matches Python Run model in fichero/models.py
///
/// Tracks queue position, status, progress, retries, and costs.
/// Each Run produces Artifacts and Traces.
struct Run: Identifiable, Codable, Hashable {
    let id: String
    var workflowId: String
    var documentIds: [String]

    // Queue
    var priority: Int

    // Status
    var status: RunStatus
    var currentStep: String?
    var progress: Double

    // Retry
    var attempt: Int
    var maxAttempts: Int
    var error: String?

    // Results
    var artifactIds: [String]

    // Cost tracking
    var tokensUsed: Int
    var costUsd: Double

    // Runtime config
    var config: [String: AnyCodable]

    // Timing
    var queuedAt: Date
    var startedAt: Date?
    var completedAt: Date?

    enum CodingKeys: String, CodingKey {
        case id
        case workflowId = "workflow_id"
        case documentIds = "document_ids"
        case priority
        case status
        case currentStep = "current_step"
        case progress
        case attempt
        case maxAttempts = "max_attempts"
        case error
        case artifactIds = "artifact_ids"
        case tokensUsed = "tokens_used"
        case costUsd = "cost_usd"
        case config
        case queuedAt = "queued_at"
        case startedAt = "started_at"
        case completedAt = "completed_at"
    }

    init(
        id: String = UUID().uuidString,
        workflowId: String,
        documentIds: [String] = [],
        priority: Int = 0,
        status: RunStatus = .queued,
        currentStep: String? = nil,
        progress: Double = 0.0,
        attempt: Int = 1,
        maxAttempts: Int = 3,
        error: String? = nil,
        artifactIds: [String] = [],
        tokensUsed: Int = 0,
        costUsd: Double = 0.0,
        config: [String: AnyCodable] = [:],
        queuedAt: Date = Date(),
        startedAt: Date? = nil,
        completedAt: Date? = nil
    ) {
        self.id = id
        self.workflowId = workflowId
        self.documentIds = documentIds
        self.priority = priority
        self.status = status
        self.currentStep = currentStep
        self.progress = progress
        self.attempt = attempt
        self.maxAttempts = maxAttempts
        self.error = error
        self.artifactIds = artifactIds
        self.tokensUsed = tokensUsed
        self.costUsd = costUsd
        self.config = config
        self.queuedAt = queuedAt
        self.startedAt = startedAt
        self.completedAt = completedAt
    }
}

// MARK: - Run Helpers

extension Run {
    /// Duration of the run (if completed or running)
    var duration: TimeInterval? {
        guard let start = startedAt else { return nil }
        let end = completedAt ?? Date()
        return end.timeIntervalSince(start)
    }

    /// Formatted duration string
    var durationString: String? {
        guard let duration = duration else { return nil }
        let formatter = DateComponentsFormatter()
        formatter.allowedUnits = [.hour, .minute, .second]
        formatter.unitsStyle = .abbreviated
        return formatter.string(from: duration)
    }

    /// Progress percentage (0-100)
    var progressPercent: Int {
        Int(progress * 100)
    }

    /// Cost formatted as currency
    var costFormatted: String {
        String(format: "$%.4f", costUsd)
    }

    /// Whether the run can be retried
    var canRetry: Bool {
        status == .failed && attempt < maxAttempts
    }
}
