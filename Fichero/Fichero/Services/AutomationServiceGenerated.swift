import Foundation
import OSLog
import FicheroAPIClient
import OpenAPIRuntime

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "AutomationServiceGenerated")

/// Service for automation operations (schedules and triggers) using generated OpenAPI client
@MainActor
class AutomationServiceGenerated: ObservableObject {
    private let client: FicheroClient

    /// Initialize with FicheroClient (preferred)
    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    // MARK: - Schedule Operations

    /// List all schedules
    func listSchedules(status: String? = nil, workflowId: String? = nil, limit: Int = 100) async throws -> [Components.Schemas.ScheduleResponse] {
        let response = try await client.api.listSchedulesApiSchedulesGet(.init(
            query: .init(status: status, workflowId: workflowId, limit: limit),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        ))

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw AutomationServiceGeneratedError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw AutomationServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    /// Get schedule by ID
    func getSchedule(scheduleId: String) async throws -> Components.Schemas.ScheduleResponse {
        let response = try await client.api.getScheduleApiSchedulesScheduleIdGet(.init(
            path: .init(scheduleId: scheduleId),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        ))

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw AutomationServiceGeneratedError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw AutomationServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    /// Delete a schedule
    func deleteSchedule(scheduleId: String) async throws {
        let response = try await client.api.deleteScheduleApiSchedulesScheduleIdDelete(.init(
            path: .init(scheduleId: scheduleId),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        ))

        switch response {
        case .ok:
            return
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw AutomationServiceGeneratedError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw AutomationServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    /// Pause a schedule
    func pauseSchedule(scheduleId: String) async throws -> Components.Schemas.ScheduleResponse {
        let response = try await client.api.pauseScheduleApiSchedulesScheduleIdPausePost(.init(
            path: .init(scheduleId: scheduleId),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        ))

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw AutomationServiceGeneratedError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw AutomationServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    /// Resume a schedule
    func resumeSchedule(scheduleId: String) async throws -> Components.Schemas.ScheduleResponse {
        let response = try await client.api.resumeScheduleApiSchedulesScheduleIdResumePost(.init(
            path: .init(scheduleId: scheduleId),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        ))

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw AutomationServiceGeneratedError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw AutomationServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    /// Trigger a schedule immediately
    func triggerSchedule(scheduleId: String) async throws -> Components.Schemas.ScheduleRunResponse {
        let response = try await client.api.triggerScheduleApiSchedulesScheduleIdTriggerPost(.init(
            path: .init(scheduleId: scheduleId),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        ))

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw AutomationServiceGeneratedError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw AutomationServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    /// Update a schedule (rename)
    func updateSchedule(scheduleId: String, newName: String) async throws -> Components.Schemas.ScheduleResponse {
        // Create update request with just the name
        let updateRequest = Components.Schemas.UpdateScheduleRequest(name: newName)

        let response = try await client.api.updateScheduleApiSchedulesScheduleIdPut(.init(
            path: .init(scheduleId: scheduleId),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? ""),
            body: .json(updateRequest)
        ))

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw AutomationServiceGeneratedError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw AutomationServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    /// Get schedule run history
    func getScheduleRuns(scheduleId: String, limit: Int = 50) async throws -> [Components.Schemas.ScheduleRunResponse] {
        let response = try await client.api.getScheduleRunsApiSchedulesScheduleIdRunsGet(.init(
            path: .init(scheduleId: scheduleId),
            query: .init(limit: limit),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        ))

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw AutomationServiceGeneratedError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw AutomationServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    // MARK: - Trigger Operations

    /// List all triggers
    func listTriggers(status: String? = nil, workflowId: String? = nil, limit: Int = 100) async throws -> [Components.Schemas.TriggerResponse] {
        let response = try await client.api.listTriggersApiTriggersGet(.init(
            query: .init(status: status, workflowId: workflowId, limit: limit),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        ))

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw AutomationServiceGeneratedError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw AutomationServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    /// Get trigger by ID
    func getTrigger(triggerId: String) async throws -> Components.Schemas.TriggerResponse {
        let response = try await client.api.getTriggerApiTriggersTriggerIdGet(.init(
            path: .init(triggerId: triggerId),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        ))

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw AutomationServiceGeneratedError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw AutomationServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    /// Delete a trigger
    func deleteTrigger(triggerId: String) async throws {
        let response = try await client.api.deleteTriggerApiTriggersTriggerIdDelete(.init(
            path: .init(triggerId: triggerId),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        ))

        switch response {
        case .ok:
            return
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw AutomationServiceGeneratedError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw AutomationServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    /// Pause a trigger
    func pauseTrigger(triggerId: String) async throws -> Components.Schemas.TriggerResponse {
        let response = try await client.api.pauseTriggerApiTriggersTriggerIdPausePost(.init(
            path: .init(triggerId: triggerId),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        ))

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw AutomationServiceGeneratedError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw AutomationServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    /// Resume a trigger
    func resumeTrigger(triggerId: String) async throws -> Components.Schemas.TriggerResponse {
        let response = try await client.api.resumeTriggerApiTriggersTriggerIdResumePost(.init(
            path: .init(triggerId: triggerId),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        ))

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw AutomationServiceGeneratedError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw AutomationServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    /// Update a trigger (rename)
    func updateTrigger(triggerId: String, newName: String) async throws -> Components.Schemas.TriggerResponse {
        // Create update request with just the name
        let updateRequest = Components.Schemas.UpdateTriggerRequest(name: newName)

        let response = try await client.api.updateTriggerApiTriggersTriggerIdPut(.init(
            path: .init(triggerId: triggerId),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? ""),
            body: .json(updateRequest)
        ))

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw AutomationServiceGeneratedError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw AutomationServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    /// Get trigger execution history
    func getTriggerExecutions(triggerId: String, limit: Int = 50) async throws -> [Components.Schemas.TriggerExecutionResponse] {
        let response = try await client.api.getTriggerExecutionsApiTriggersTriggerIdExecutionsGet(.init(
            path: .init(triggerId: triggerId),
            query: .init(limit: limit),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        ))

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw AutomationServiceGeneratedError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw AutomationServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }
}

// MARK: - App Type Convenience Methods

private let iso8601Formatter: ISO8601DateFormatter = {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return formatter
}()

extension AutomationServiceGenerated {
    /// List schedules returning app ScheduleInfo type
    func listSchedules(status: String? = nil, workflowId: String? = nil, limit: Int = 100) async throws -> [ScheduleInfo] {
        let schedules: [Components.Schemas.ScheduleResponse] = try await listSchedules(status: status, workflowId: workflowId, limit: limit)
        return schedules.map { convertToScheduleInfo($0) }
    }

    /// List triggers returning app TriggerInfo type
    func listTriggers(status: String? = nil, workflowId: String? = nil, limit: Int = 100) async throws -> [TriggerInfo] {
        let triggers: [Components.Schemas.TriggerResponse] = try await listTriggers(status: status, workflowId: workflowId, limit: limit)
        return triggers.map { convertToTriggerInfo($0) }
    }

    /// Pause schedule returning app ScheduleInfo type
    func pauseScheduleAsInfo(scheduleId: String) async throws -> ScheduleInfo {
        let schedule = try await pauseSchedule(scheduleId: scheduleId)
        return convertToScheduleInfo(schedule)
    }

    /// Resume schedule returning app ScheduleInfo type
    func resumeScheduleAsInfo(scheduleId: String) async throws -> ScheduleInfo {
        let schedule = try await resumeSchedule(scheduleId: scheduleId)
        return convertToScheduleInfo(schedule)
    }

    /// Trigger schedule returning app ScheduleRunInfo type
    func triggerScheduleAsInfo(scheduleId: String) async throws -> ScheduleRunInfo {
        let run = try await triggerSchedule(scheduleId: scheduleId)
        return convertToScheduleRunInfo(run)
    }

    /// Pause trigger returning app TriggerInfo type
    func pauseTriggerAsInfo(triggerId: String) async throws -> TriggerInfo {
        let trigger = try await pauseTrigger(triggerId: triggerId)
        return convertToTriggerInfo(trigger)
    }

    /// Resume trigger returning app TriggerInfo type
    func resumeTriggerAsInfo(triggerId: String) async throws -> TriggerInfo {
        let trigger = try await resumeTrigger(triggerId: triggerId)
        return convertToTriggerInfo(trigger)
    }

    // MARK: - Type Conversions

    private func convertToScheduleInfo(_ response: Components.Schemas.ScheduleResponse) -> ScheduleInfo {
        // Convert inputs from generated type to [String: String]
        var inputs: [String: String]?
        if let inputsDict = response.inputs.additionalProperties.value as? [String: Any] {
            var converted: [String: String] = [:]
            for (key, value) in inputsDict {
                if let str = value as? String {
                    converted[key] = str
                } else {
                    converted[key] = String(describing: value)
                }
            }
            inputs = converted.isEmpty ? nil : converted
        }

        // Convert batch items
        var batchItems: [[String: String]]?
        let genBatchItems = response.batchItems
        if !genBatchItems.isEmpty {
            let converted = genBatchItems.compactMap { item -> [String: String]? in
                guard let itemDict = item.additionalProperties.value as? [String: Any] else { return nil }
                var dict: [String: String] = [:]
                for (key, value) in itemDict {
                    if let str = value as? String {
                        dict[key] = str
                    } else {
                        dict[key] = String(describing: value)
                    }
                }
                return dict.isEmpty ? nil : dict
            }
            batchItems = converted.isEmpty ? nil : converted
        }

        return ScheduleInfo(
            scheduleId: response.scheduleId,
            name: response.name,
            workflowId: response.workflowId,
            scheduleType: response.scheduleType,
            cronExpression: response.cronExpression,
            intervalSeconds: response.intervalSeconds,
            runAt: response.runAt.map { iso8601Formatter.string(from: $0) },
            timezone: response.timezone,
            status: response.status,
            inputs: inputs,
            useBatch: response.useBatch,
            batchItems: batchItems,
            maxConcurrent: response.maxConcurrent,
            createdAt: iso8601Formatter.string(from: response.createdAt),
            updatedAt: iso8601Formatter.string(from: response.updatedAt),
            lastRunAt: response.lastRunAt.map { iso8601Formatter.string(from: $0) },
            nextRunAt: response.nextRunAt.map { iso8601Formatter.string(from: $0) },
            runCount: response.runCount,
            errorMessage: response.errorMessage
        )
    }

    private func convertToScheduleRunInfo(_ response: Components.Schemas.ScheduleRunResponse) -> ScheduleRunInfo {
        ScheduleRunInfo(
            runId: response.runId,
            scheduleId: response.scheduleId,
            startedAt: iso8601Formatter.string(from: response.startedAt),
            completedAt: response.completedAt.map { iso8601Formatter.string(from: $0) },
            status: response.status,
            batchId: response.batchId,
            error: response.error
        )
    }

    private func convertToTriggerInfo(_ response: Components.Schemas.TriggerResponse) -> TriggerInfo {
        // Convert inputs template
        var inputsTemplate: [String: String]?
        if let templateDict = response.inputsTemplate.additionalProperties.value as? [String: Any] {
            var converted: [String: String] = [:]
            for (key, value) in templateDict {
                if let str = value as? String {
                    converted[key] = str
                } else {
                    converted[key] = String(describing: value)
                }
            }
            inputsTemplate = converted.isEmpty ? nil : converted
        }

        return TriggerInfo(
            triggerId: response.triggerId,
            name: response.name,
            workflowId: response.workflowId,
            watchPath: response.watchPath,
            recursive: response.recursive,
            events: response.events,
            filterMode: response.filterMode,
            filterPattern: response.filterPattern,
            filterExtensions: response.filterExtensions,
            excludePatterns: response.excludePatterns,
            debounceSeconds: response.debounceSeconds,
            batchDelaySeconds: response.batchDelaySeconds,
            inputsTemplate: inputsTemplate,
            status: response.status,
            useBatch: response.useBatch,
            maxConcurrent: response.maxConcurrent,
            createdAt: iso8601Formatter.string(from: response.createdAt),
            updatedAt: iso8601Formatter.string(from: response.updatedAt),
            lastTriggeredAt: response.lastTriggeredAt.map { iso8601Formatter.string(from: $0) },
            triggerCount: response.triggerCount,
            errorMessage: response.errorMessage
        )
    }

    private func convertToTriggerExecutionInfo(_ response: Components.Schemas.TriggerExecutionResponse) -> TriggerExecutionInfo {
        TriggerExecutionInfo(
            executionId: response.executionId,
            triggerId: response.triggerId,
            triggeredAt: iso8601Formatter.string(from: response.triggeredAt),
            filePaths: response.filePaths,
            batchId: response.batchId,
            status: response.status,
            error: response.error,
            completedAt: response.completedAt.map { iso8601Formatter.string(from: $0) }
        )
    }
}

// MARK: - Error Types

enum AutomationServiceGeneratedError: LocalizedError {
    case validationError(String)
    case unexpectedResponse(Int)

    var errorDescription: String? {
        switch self {
        case .validationError(let message):
            return "Validation error: \(message)"
        case .unexpectedResponse(let statusCode):
            return "Unexpected response: HTTP \(statusCode)"
        }
    }
}
