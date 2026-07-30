import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "AutomationAPIService")

/// Service for automation operations (schedules and triggers).
/// NOTE: The corresponding backend routes (schedules.py, triggers.py) exist but are not
/// registered in main.py, so the OpenAPI schema never included them. All methods return
/// empty results until the routes are properly registered.
@MainActor
@Observable
class AutomationAPIService {
    private let client: FicheroClient

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    // MARK: - Schedule Operations

    func listSchedules(status: String? = nil, workflowId: String? = nil, limit: Int = 100) async throws -> [ScheduleInfo] {
        [] // Backend routes not registered in main.py
    }

    func pauseSchedule(scheduleId: String) async throws -> ScheduleInfo {
        throw AutomationAPIServiceError.notImplemented
    }

    func resumeSchedule(scheduleId: String) async throws -> ScheduleInfo {
        throw AutomationAPIServiceError.notImplemented
    }

    func triggerSchedule(scheduleId: String) async throws -> ScheduleRunInfo {
        throw AutomationAPIServiceError.notImplemented
    }

    func deleteSchedule(scheduleId: String) async throws {
        throw AutomationAPIServiceError.notImplemented
    }

    // MARK: - Trigger Operations

    func listTriggers(status: String? = nil, workflowId: String? = nil, limit: Int = 100) async throws -> [TriggerInfo] {
        [] // Backend routes not registered in main.py
    }

    func pauseTrigger(triggerId: String) async throws -> TriggerInfo {
        throw AutomationAPIServiceError.notImplemented
    }

    func resumeTrigger(triggerId: String) async throws -> TriggerInfo {
        throw AutomationAPIServiceError.notImplemented
    }

    func deleteTrigger(triggerId: String) async throws {
        throw AutomationAPIServiceError.notImplemented
    }

    func updateSchedule(scheduleId: String, newName: String) async throws {
        throw AutomationAPIServiceError.notImplemented
    }

    func updateTrigger(triggerId: String, newName: String) async throws {
        throw AutomationAPIServiceError.notImplemented
    }
}

enum AutomationAPIServiceError: LocalizedError {
    case notImplemented

    var errorDescription: String? {
        switch self {
        case .notImplemented:
            return "Backend routes not registered in main.py"
        }
    }
}
