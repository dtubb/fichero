import FicheroAPIClient
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
        let response = try await apiClient.api.createScheduleApiSchedulesPost(
            .init(body: .json(try .init(app: request)))
        )
        switch response {
        case .ok(let ok):
            return ScheduleInfo(response: try ok.body.json)
        case .unprocessableContent(let error):
            throw AutomationServiceError.validationError(
                (try? error.body.json)?.detail?.description ?? "Validation error"
            )
        default:
            throw AutomationServiceError.unexpectedResponse
        }
    }

    /// List all schedules
    func listSchedules(
        status: String? = nil,
        workflowId: String? = nil,
        limit: Int = 100
    ) async throws -> [ScheduleInfo] {
        let response = try await apiClient.api.listSchedulesApiSchedulesGet(
            .init(query: .init(status: status, workflowId: workflowId, limit: limit))
        )
        switch response {
        case .ok(let ok):
            return try ok.body.json.items.map { ScheduleInfo(response: $0) }
        case .unprocessableContent(let error):
            throw AutomationServiceError.validationError(
                (try? error.body.json)?.detail?.description ?? "Validation error"
            )
        default:
            throw AutomationServiceError.unexpectedResponse
        }
    }

    /// Get schedule by ID
    func getSchedule(scheduleId: String) async throws -> ScheduleInfo {
        try validateId(scheduleId)
        let response = try await apiClient.api.getScheduleApiSchedulesScheduleIdGet(
            .init(path: .init(scheduleId: scheduleId))
        )
        switch response {
        case .ok(let ok):
            return ScheduleInfo(response: try ok.body.json)
        case .unprocessableContent(let error):
            throw AutomationServiceError.validationError(
                (try? error.body.json)?.detail?.description ?? "Validation error"
            )
        default:
            throw AutomationServiceError.unexpectedResponse
        }
    }

    /// Delete a schedule
    func deleteSchedule(scheduleId: String) async throws {
        try validateId(scheduleId)
        let response = try await apiClient.api.deleteScheduleApiSchedulesScheduleIdDelete(
            .init(path: .init(scheduleId: scheduleId))
        )
        switch response {
        case .ok:
            return
        case .unprocessableContent(let error):
            throw AutomationServiceError.validationError(
                (try? error.body.json)?.detail?.description ?? "Validation error"
            )
        default:
            throw AutomationServiceError.unexpectedResponse
        }
    }

    /// Pause a schedule
    func pauseSchedule(scheduleId: String) async throws -> ScheduleInfo {
        try validateId(scheduleId)
        let response = try await apiClient.api.pauseScheduleApiSchedulesScheduleIdPausePost(
            .init(path: .init(scheduleId: scheduleId))
        )
        switch response {
        case .ok(let ok):
            return ScheduleInfo(response: try ok.body.json)
        case .unprocessableContent(let error):
            throw AutomationServiceError.validationError(
                (try? error.body.json)?.detail?.description ?? "Validation error"
            )
        default:
            throw AutomationServiceError.unexpectedResponse
        }
    }

    /// Resume a schedule
    func resumeSchedule(scheduleId: String) async throws -> ScheduleInfo {
        try validateId(scheduleId)
        let response = try await apiClient.api.resumeScheduleApiSchedulesScheduleIdResumePost(
            .init(path: .init(scheduleId: scheduleId))
        )
        switch response {
        case .ok(let ok):
            return ScheduleInfo(response: try ok.body.json)
        case .unprocessableContent(let error):
            throw AutomationServiceError.validationError(
                (try? error.body.json)?.detail?.description ?? "Validation error"
            )
        default:
            throw AutomationServiceError.unexpectedResponse
        }
    }

    /// Trigger a schedule to run now
    func triggerSchedule(scheduleId: String) async throws -> ScheduleRunInfo {
        try validateId(scheduleId)
        let response = try await apiClient.api.triggerScheduleApiSchedulesScheduleIdTriggerPost(
            .init(path: .init(scheduleId: scheduleId))
        )
        switch response {
        case .ok(let ok):
            return ScheduleRunInfo(response: try ok.body.json)
        case .unprocessableContent(let error):
            throw AutomationServiceError.validationError(
                (try? error.body.json)?.detail?.description ?? "Validation error"
            )
        default:
            throw AutomationServiceError.unexpectedResponse
        }
    }

    /// Get schedule run history
    func getScheduleRuns(scheduleId: String, limit: Int = 50) async throws -> [ScheduleRunInfo] {
        try validateId(scheduleId)
        let response = try await apiClient.api.getScheduleRunsApiSchedulesScheduleIdRunsGet(
            .init(path: .init(scheduleId: scheduleId), query: .init(limit: limit))
        )
        switch response {
        case .ok(let ok):
            return try ok.body.json.items.map { ScheduleRunInfo(response: $0) }
        case .unprocessableContent(let error):
            throw AutomationServiceError.validationError(
                (try? error.body.json)?.detail?.description ?? "Validation error"
            )
        default:
            throw AutomationServiceError.unexpectedResponse
        }
    }

    // MARK: - Trigger Operations

    /// Create a new file trigger
    func createTrigger(request: CreateTriggerRequest) async throws -> TriggerInfo {
        let response = try await apiClient.api.createTriggerApiTriggersPost(
            .init(body: .json(.init(app: request)))
        )
        switch response {
        case .ok(let ok):
            return TriggerInfo(response: try ok.body.json)
        case .unprocessableContent(let error):
            throw AutomationServiceError.validationError(
                (try? error.body.json)?.detail?.description ?? "Validation error"
            )
        default:
            throw AutomationServiceError.unexpectedResponse
        }
    }

    /// List all triggers
    func listTriggers(
        status: String? = nil,
        workflowId: String? = nil,
        limit: Int = 100
    ) async throws -> [TriggerInfo] {
        let response = try await apiClient.api.listTriggersApiTriggersGet(
            .init(query: .init(status: status, workflowId: workflowId, limit: limit))
        )
        switch response {
        case .ok(let ok):
            return try ok.body.json.items.map { TriggerInfo(response: $0) }
        case .unprocessableContent(let error):
            throw AutomationServiceError.validationError(
                (try? error.body.json)?.detail?.description ?? "Validation error"
            )
        default:
            throw AutomationServiceError.unexpectedResponse
        }
    }

    /// Get trigger by ID
    func getTrigger(triggerId: String) async throws -> TriggerInfo {
        try validateId(triggerId)
        let response = try await apiClient.api.getTriggerApiTriggersTriggerIdGet(
            .init(path: .init(triggerId: triggerId))
        )
        switch response {
        case .ok(let ok):
            return TriggerInfo(response: try ok.body.json)
        case .unprocessableContent(let error):
            throw AutomationServiceError.validationError(
                (try? error.body.json)?.detail?.description ?? "Validation error"
            )
        default:
            throw AutomationServiceError.unexpectedResponse
        }
    }

    /// Delete a trigger
    func deleteTrigger(triggerId: String) async throws {
        try validateId(triggerId)
        let response = try await apiClient.api.deleteTriggerApiTriggersTriggerIdDelete(
            .init(path: .init(triggerId: triggerId))
        )
        switch response {
        case .ok:
            return
        case .unprocessableContent(let error):
            throw AutomationServiceError.validationError(
                (try? error.body.json)?.detail?.description ?? "Validation error"
            )
        default:
            throw AutomationServiceError.unexpectedResponse
        }
    }

    /// Pause a trigger
    func pauseTrigger(triggerId: String) async throws -> TriggerInfo {
        try validateId(triggerId)
        let response = try await apiClient.api.pauseTriggerApiTriggersTriggerIdPausePost(
            .init(path: .init(triggerId: triggerId))
        )
        switch response {
        case .ok(let ok):
            return TriggerInfo(response: try ok.body.json)
        case .unprocessableContent(let error):
            throw AutomationServiceError.validationError(
                (try? error.body.json)?.detail?.description ?? "Validation error"
            )
        default:
            throw AutomationServiceError.unexpectedResponse
        }
    }

    /// Resume a trigger
    func resumeTrigger(triggerId: String) async throws -> TriggerInfo {
        try validateId(triggerId)
        let response = try await apiClient.api.resumeTriggerApiTriggersTriggerIdResumePost(
            .init(path: .init(triggerId: triggerId))
        )
        switch response {
        case .ok(let ok):
            return TriggerInfo(response: try ok.body.json)
        case .unprocessableContent(let error):
            throw AutomationServiceError.validationError(
                (try? error.body.json)?.detail?.description ?? "Validation error"
            )
        default:
            throw AutomationServiceError.unexpectedResponse
        }
    }

    /// Get trigger execution history
    func getTriggerExecutions(triggerId: String, limit: Int = 50) async throws -> [TriggerExecutionInfo] {
        try validateId(triggerId)
        let response = try await apiClient.api.getTriggerExecutionsApiTriggersTriggerIdExecutionsGet(
            .init(path: .init(triggerId: triggerId), query: .init(limit: limit))
        )
        switch response {
        case .ok(let ok):
            return try ok.body.json.items.map { TriggerExecutionInfo(response: $0) }
        case .unprocessableContent(let error):
            throw AutomationServiceError.validationError(
                (try? error.body.json)?.detail?.description ?? "Validation error"
            )
        default:
            throw AutomationServiceError.unexpectedResponse
        }
    }
}
