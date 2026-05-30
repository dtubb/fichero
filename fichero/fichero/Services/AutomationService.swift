import Foundation
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "AutomationService")

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
        for pattern in invalidPatterns where id.lowercased().contains(pattern) {
            logger.error("Invalid ID detected: contains forbidden pattern '\(pattern)'")
            throw AutomationServiceError.invalidInput("Invalid ID format")
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
    func listSchedules(
        status: String? = nil,
        workflowId: String? = nil,
        limit: Int = 100
    ) async throws -> [ScheduleInfo] {
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
    func listTriggers(
        status: String? = nil,
        workflowId: String? = nil,
        limit: Int = 100
    ) async throws -> [TriggerInfo] {
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
