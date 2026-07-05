import Observation
import Foundation
import OSLog
import FicheroAPIClient
import OpenAPIRuntime

private let logger = Logger(subsystem: "app.fichero.fichero", category: "AutomationServiceGenerated")

/// Service for automation operations (schedules and triggers).
/// NOTE: The corresponding backend routes (schedules.py, triggers.py) exist but are not
/// registered in main.py, so the OpenAPI schema never included them. All methods return
/// empty results until the routes are properly registered.
@MainActor
@Observable
class AutomationServiceGenerated {
    private let client: FicheroClient

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    // MARK: - Schedule Operations

    func listSchedules(status: String? = nil, workflowId: String? = nil, limit: Int = 100) async throws -> [ScheduleInfo] {
        [] // Backend routes not registered in main.py
    }

    func pauseSchedule(scheduleId: String) async throws -> ScheduleInfo {
        throw AutomationServiceGeneratedError.notImplemented
    }

    func resumeSchedule(scheduleId: String) async throws -> ScheduleInfo {
        throw AutomationServiceGeneratedError.notImplemented
    }

    func triggerSchedule(scheduleId: String) async throws -> ScheduleRunInfo {
        throw AutomationServiceGeneratedError.notImplemented
    }

    func deleteSchedule(scheduleId: String) async throws {
        throw AutomationServiceGeneratedError.notImplemented
    }

    // MARK: - Trigger Operations

    func listTriggers(status: String? = nil, workflowId: String? = nil, limit: Int = 100) async throws -> [TriggerInfo] {
        [] // Backend routes not registered in main.py
    }

    func pauseTrigger(triggerId: String) async throws -> TriggerInfo {
        throw AutomationServiceGeneratedError.notImplemented
    }

    func resumeTrigger(triggerId: String) async throws -> TriggerInfo {
        throw AutomationServiceGeneratedError.notImplemented
    }

    func deleteTrigger(triggerId: String) async throws {
        throw AutomationServiceGeneratedError.notImplemented
    }

    func updateSchedule(scheduleId: String, newName: String) async throws {
        throw AutomationServiceGeneratedError.notImplemented
    }

    func updateTrigger(triggerId: String, newName: String) async throws {
        throw AutomationServiceGeneratedError.notImplemented
    }
}

enum AutomationServiceGeneratedError: LocalizedError {
    case notImplemented

    var errorDescription: String? {
        switch self {
        case .notImplemented:
            return "Backend routes not registered in main.py"
        }
    }
}
