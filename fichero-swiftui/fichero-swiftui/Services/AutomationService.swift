import Foundation
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "AutomationService")

/// Service for interacting with the Automation API (schedules and triggers)
/// Note: Data refresh is handled by SidebarView via callback pattern (onRefresh)
@MainActor
class AutomationService {
    private let apiClient: APIClient

    init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    // MARK: - Input Validation

    /// Validate an ID to prevent path traversal attacks
    private func validateId(_ id: String) throws {
        // Reject IDs containing path traversal sequences or special characters
        let invalidPatterns = ["..", "/", "\\", "%2e", "%2f", "%5c"]
        for pattern in invalidPatterns {
            if id.lowercased().contains(pattern) {
                logger.error("Invalid ID detected: contains forbidden pattern '\(pattern)'")
                throw AutomationServiceError.invalidInput("Invalid ID format")
            }
        }
        // IDs should only contain alphanumeric, hyphen, and underscore
        let allowedCharacters = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-_"))
        if id.unicodeScalars.contains(where: { !allowedCharacters.contains($0) }) {
            logger.error("Invalid ID detected: contains invalid characters")
            throw AutomationServiceError.invalidInput("Invalid ID format")
        }
    }

    // MARK: - Schedule Operations

    /// Create a new schedule
    func createSchedule(request: CreateScheduleRequest) async throws -> ScheduleInfo {
        let response: ScheduleInfo = try await apiClient.post("/schedules", body: request)
        return response
    }

    /// List all schedules
    func listSchedules(status: String? = nil, workflowId: String? = nil, limit: Int = 100) async throws -> [ScheduleInfo] {
        var queryParams: [String] = ["limit=\(limit)"]
        if let status = status {
            queryParams.append("status=\(status)")
        }
        if let workflowId = workflowId {
            queryParams.append("workflow_id=\(workflowId)")
        }
        let queryString = "?\(queryParams.joined(separator: "&"))"
        let response: [ScheduleInfo] = try await apiClient.get("/schedules\(queryString)")
        return response
    }

    /// Get schedule by ID
    func getSchedule(scheduleId: String) async throws -> ScheduleInfo {
        try validateId(scheduleId)
        let response: ScheduleInfo = try await apiClient.get("/schedules/\(scheduleId)")
        return response
    }

    /// Delete a schedule
    func deleteSchedule(scheduleId: String) async throws {
        try validateId(scheduleId)
        try await apiClient.delete("/schedules/\(scheduleId)")
    }

    /// Pause a schedule
    func pauseSchedule(scheduleId: String) async throws -> ScheduleInfo {
        try validateId(scheduleId)
        let response: ScheduleInfo = try await apiClient.post("/schedules/\(scheduleId)/pause")
        return response
    }

    /// Resume a schedule
    func resumeSchedule(scheduleId: String) async throws -> ScheduleInfo {
        try validateId(scheduleId)
        let response: ScheduleInfo = try await apiClient.post("/schedules/\(scheduleId)/resume")
        return response
    }

    /// Trigger a schedule to run now
    func triggerSchedule(scheduleId: String) async throws -> ScheduleRunInfo {
        try validateId(scheduleId)
        let response: ScheduleRunInfo = try await apiClient.post("/schedules/\(scheduleId)/trigger")
        return response
    }

    /// Get schedule run history
    func getScheduleRuns(scheduleId: String, limit: Int = 50) async throws -> [ScheduleRunInfo] {
        try validateId(scheduleId)
        let response: [ScheduleRunInfo] = try await apiClient.get(
            "/schedules/\(scheduleId)/runs?limit=\(limit)"
        )
        return response
    }

    // MARK: - Trigger Operations

    /// Create a new file trigger
    func createTrigger(request: CreateTriggerRequest) async throws -> TriggerInfo {
        let response: TriggerInfo = try await apiClient.post("/triggers", body: request)
        return response
    }

    /// List all triggers
    func listTriggers(status: String? = nil, workflowId: String? = nil, limit: Int = 100) async throws -> [TriggerInfo] {
        var queryParams: [String] = ["limit=\(limit)"]
        if let status = status {
            queryParams.append("status=\(status)")
        }
        if let workflowId = workflowId {
            queryParams.append("workflow_id=\(workflowId)")
        }
        let queryString = "?\(queryParams.joined(separator: "&"))"
        let response: [TriggerInfo] = try await apiClient.get("/triggers\(queryString)")
        return response
    }

    /// Get trigger by ID
    func getTrigger(triggerId: String) async throws -> TriggerInfo {
        try validateId(triggerId)
        let response: TriggerInfo = try await apiClient.get("/triggers/\(triggerId)")
        return response
    }

    /// Delete a trigger
    func deleteTrigger(triggerId: String) async throws {
        try validateId(triggerId)
        try await apiClient.delete("/triggers/\(triggerId)")
    }

    /// Pause a trigger
    func pauseTrigger(triggerId: String) async throws -> TriggerInfo {
        try validateId(triggerId)
        let response: TriggerInfo = try await apiClient.post("/triggers/\(triggerId)/pause")
        return response
    }

    /// Resume a trigger
    func resumeTrigger(triggerId: String) async throws -> TriggerInfo {
        try validateId(triggerId)
        let response: TriggerInfo = try await apiClient.post("/triggers/\(triggerId)/resume")
        return response
    }

    /// Get trigger execution history
    func getTriggerExecutions(triggerId: String, limit: Int = 50) async throws -> [TriggerExecutionInfo] {
        try validateId(triggerId)
        let response: [TriggerExecutionInfo] = try await apiClient.get(
            "/triggers/\(triggerId)/executions?limit=\(limit)"
        )
        return response
    }
}

// MARK: - Request Models

struct ScheduleConfigRequest: Codable {
    let scheduleType: String
    let cronExpression: String?
    let intervalSeconds: Int?
    let runAt: String?
    let timezone: String
    let startDate: String?
    let endDate: String?
    let maxRuns: Int?

    enum CodingKeys: String, CodingKey {
        case scheduleType = "schedule_type"
        case cronExpression = "cron_expression"
        case intervalSeconds = "interval_seconds"
        case runAt = "run_at"
        case timezone
        case startDate = "start_date"
        case endDate = "end_date"
        case maxRuns = "max_runs"
    }
}

struct CreateScheduleRequest: Codable {
    let name: String
    let workflowId: String
    let config: ScheduleConfigRequest
    let inputs: [String: String]
    let useBatch: Bool
    let batchItems: [[String: String]]
    let maxConcurrent: Int

    enum CodingKeys: String, CodingKey {
        case name
        case workflowId = "workflow_id"
        case config
        case inputs
        case useBatch = "use_batch"
        case batchItems = "batch_items"
        case maxConcurrent = "max_concurrent"
    }
}

struct TriggerConfigRequest: Codable {
    let watchPath: String
    let recursive: Bool
    let events: [String]
    let filterMode: String
    let filterPattern: String?
    let filterExtensions: [String]
    let excludePatterns: [String]
    let debounceSeconds: Double
    let batchDelaySeconds: Double

    enum CodingKeys: String, CodingKey {
        case watchPath = "watch_path"
        case recursive
        case events
        case filterMode = "filter_mode"
        case filterPattern = "filter_pattern"
        case filterExtensions = "filter_extensions"
        case excludePatterns = "exclude_patterns"
        case debounceSeconds = "debounce_seconds"
        case batchDelaySeconds = "batch_delay_seconds"
    }
}

struct CreateTriggerRequest: Codable {
    let name: String
    let workflowId: String
    let config: TriggerConfigRequest
    let inputsTemplate: [String: String]
    let useBatch: Bool
    let maxConcurrent: Int

    enum CodingKeys: String, CodingKey {
        case name
        case workflowId = "workflow_id"
        case config
        case inputsTemplate = "inputs_template"
        case useBatch = "use_batch"
        case maxConcurrent = "max_concurrent"
    }
}

// MARK: - Response Models

struct ScheduleInfo: Codable, Identifiable, Equatable, Hashable {
    let scheduleId: String
    let name: String
    let workflowId: String
    let scheduleType: String
    let cronExpression: String?
    let intervalSeconds: Int?
    let runAt: String?
    let timezone: String
    let status: String
    let inputs: [String: String]?
    let useBatch: Bool
    let batchItems: [[String: String]]?
    let maxConcurrent: Int
    let createdAt: String
    let updatedAt: String
    let lastRunAt: String?
    let nextRunAt: String?
    let runCount: Int
    let errorMessage: String?

    var id: String { scheduleId }

    enum CodingKeys: String, CodingKey {
        case scheduleId = "schedule_id"
        case name
        case workflowId = "workflow_id"
        case scheduleType = "schedule_type"
        case cronExpression = "cron_expression"
        case intervalSeconds = "interval_seconds"
        case runAt = "run_at"
        case timezone
        case status
        case inputs
        case useBatch = "use_batch"
        case batchItems = "batch_items"
        case maxConcurrent = "max_concurrent"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case lastRunAt = "last_run_at"
        case nextRunAt = "next_run_at"
        case runCount = "run_count"
        case errorMessage = "error_message"
    }

    var statusIcon: String {
        switch status {
        case "active": return "play.circle.fill"
        case "paused": return "pause.circle.fill"
        case "completed": return "checkmark.circle.fill"
        case "error": return "exclamationmark.circle.fill"
        default: return "questionmark.circle"
        }
    }

    var statusColor: String {
        switch status {
        case "active": return "green"
        case "paused": return "yellow"
        case "completed": return "gray"
        case "error": return "red"
        default: return "primary"
        }
    }

    var scheduleDescription: String {
        switch scheduleType {
        case "cron":
            return cronExpression ?? "No expression"
        case "interval":
            if let seconds = intervalSeconds {
                if seconds < 60 {
                    return "Every \(seconds) seconds"
                } else if seconds < 3600 {
                    return "Every \(seconds / 60) minutes"
                } else {
                    return "Every \(seconds / 3600) hours"
                }
            }
            return "Unknown interval"
        case "once":
            return runAt ?? "No date set"
        default:
            return scheduleType
        }
    }
}

struct ScheduleRunInfo: Codable, Identifiable {
    let runId: String
    let scheduleId: String
    let startedAt: String
    let completedAt: String?
    let status: String
    let batchId: String?
    let error: String?

    var id: String { runId }

    enum CodingKeys: String, CodingKey {
        case runId = "run_id"
        case scheduleId = "schedule_id"
        case startedAt = "started_at"
        case completedAt = "completed_at"
        case status
        case batchId = "batch_id"
        case error
    }
}

struct TriggerInfo: Codable, Identifiable, Equatable, Hashable {
    let triggerId: String
    let name: String
    let workflowId: String
    let watchPath: String
    let recursive: Bool
    let events: [String]
    let filterMode: String
    let filterPattern: String?
    let filterExtensions: [String]
    let excludePatterns: [String]
    let debounceSeconds: Double
    let batchDelaySeconds: Double
    let inputsTemplate: [String: String]?
    let status: String
    let useBatch: Bool
    let maxConcurrent: Int
    let createdAt: String
    let updatedAt: String
    let lastTriggeredAt: String?
    let triggerCount: Int
    let errorMessage: String?

    var id: String { triggerId }

    enum CodingKeys: String, CodingKey {
        case triggerId = "trigger_id"
        case name
        case workflowId = "workflow_id"
        case watchPath = "watch_path"
        case recursive
        case events
        case filterMode = "filter_mode"
        case filterPattern = "filter_pattern"
        case filterExtensions = "filter_extensions"
        case excludePatterns = "exclude_patterns"
        case debounceSeconds = "debounce_seconds"
        case batchDelaySeconds = "batch_delay_seconds"
        case inputsTemplate = "inputs_template"
        case status
        case useBatch = "use_batch"
        case maxConcurrent = "max_concurrent"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case lastTriggeredAt = "last_triggered_at"
        case triggerCount = "trigger_count"
        case errorMessage = "error_message"
    }

    var statusIcon: String {
        switch status {
        case "active": return "eye.fill"
        case "paused": return "pause.circle.fill"
        case "error": return "exclamationmark.circle.fill"
        default: return "questionmark.circle"
        }
    }

    var statusColor: String {
        switch status {
        case "active": return "green"
        case "paused": return "yellow"
        case "error": return "red"
        default: return "primary"
        }
    }

    var eventsDescription: String {
        if events.contains("any") {
            return "All events"
        }
        return events.joined(separator: ", ")
    }

    var filterDescription: String {
        switch filterMode {
        case "glob":
            return filterPattern ?? "*.*"
        case "regex":
            return filterPattern ?? ".*"
        case "extension":
            return filterExtensions.isEmpty ? "All files" : filterExtensions.joined(separator: ", ")
        default:
            return filterMode
        }
    }
}

struct TriggerExecutionInfo: Codable, Identifiable {
    let executionId: String
    let triggerId: String
    let triggeredAt: String
    let filePaths: [String]
    let batchId: String?
    let status: String
    let error: String?
    let completedAt: String?

    var id: String { executionId }

    enum CodingKeys: String, CodingKey {
        case executionId = "execution_id"
        case triggerId = "trigger_id"
        case triggeredAt = "triggered_at"
        case filePaths = "file_paths"
        case batchId = "batch_id"
        case status
        case error
        case completedAt = "completed_at"
    }
}

// MARK: - Errors

enum AutomationServiceError: LocalizedError {
    case invalidInput(String)

    var errorDescription: String? {
        switch self {
        case .invalidInput(let message):
            return "Invalid input: \(message)"
        }
    }
}
