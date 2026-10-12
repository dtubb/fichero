import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "AutomationAPIService")

/// A project's schedules and triggers, as the sidebar lists and acts on them, through the generated client (#5712).
///
/// This used to answer every call with nothing (an empty list, or "not implemented"), on a note that the engine's
/// routes were not registered; they are (`/api/schedules…`, `/api/triggers…` in the contract), so the sidebar never
/// listed a schedule or trigger and their verbs did nothing. Every read and action now goes through the ONE typed
/// implementation (`AutomationService`, which the schedule and trigger editors already use) on this project's own
/// generated client; renaming is the update route with only the name.
@MainActor
@Observable
class AutomationAPIService {
    private let client: FicheroClient
    @ObservationIgnored private lazy var service = AutomationService(apiClient: APIClient(client: client))

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    // MARK: - Schedule Operations

    func listSchedules(status: String? = nil, workflowId: String? = nil, limit: Int = 100) async throws -> [ScheduleInfo] {
        try await service.listSchedules(status: status, workflowId: workflowId, limit: limit)
    }

    func pauseSchedule(scheduleId: String) async throws -> ScheduleInfo {
        try await service.pauseSchedule(scheduleId: scheduleId)
    }

    func resumeSchedule(scheduleId: String) async throws -> ScheduleInfo {
        try await service.resumeSchedule(scheduleId: scheduleId)
    }

    func triggerSchedule(scheduleId: String) async throws -> ScheduleRunInfo {
        try await service.triggerSchedule(scheduleId: scheduleId)
    }

    func deleteSchedule(scheduleId: String) async throws {
        try await service.deleteSchedule(scheduleId: scheduleId)
    }

    // MARK: - Trigger Operations

    func listTriggers(status: String? = nil, workflowId: String? = nil, limit: Int = 100) async throws -> [TriggerInfo] {
        try await service.listTriggers(status: status, workflowId: workflowId, limit: limit)
    }

    func pauseTrigger(triggerId: String) async throws -> TriggerInfo {
        try await service.pauseTrigger(triggerId: triggerId)
    }

    func resumeTrigger(triggerId: String) async throws -> TriggerInfo {
        try await service.resumeTrigger(triggerId: triggerId)
    }

    func deleteTrigger(triggerId: String) async throws {
        try await service.deleteTrigger(triggerId: triggerId)
    }

    // MARK: - Rename (the update route, with only the name)

    func updateSchedule(scheduleId: String, newName: String) async throws {
        let response = try await client.api.updateScheduleApiSchedulesScheduleIdPut(
            path: .init(scheduleId: scheduleId), body: .json(.init(name: newName))
        )
        switch response {
        case .ok:
            return
        case .unprocessableContent(let error):
            throw AutomationAPIServiceError.refused((try? error.body.json)?.detail?.description ?? "the engine refused it")
        case .undocumented(let code, let payload):
            throw AutomationAPIServiceError.refused(await EngineErrorDetail.message(from: payload) ?? "HTTP \(code)")
        }
    }

    func updateTrigger(triggerId: String, newName: String) async throws {
        let response = try await client.api.updateTriggerApiTriggersTriggerIdPut(
            path: .init(triggerId: triggerId), body: .json(.init(name: newName))
        )
        switch response {
        case .ok:
            return
        case .unprocessableContent(let error):
            throw AutomationAPIServiceError.refused((try? error.body.json)?.detail?.description ?? "the engine refused it")
        case .undocumented(let code, let payload):
            throw AutomationAPIServiceError.refused(await EngineErrorDetail.message(from: payload) ?? "HTTP \(code)")
        }
    }
}

enum AutomationAPIServiceError: LocalizedError, Equatable {
    case refused(String)

    var errorDescription: String? {
        switch self {
        case .refused(let why): "The engine refused the change: \(why)"
        }
    }
}
