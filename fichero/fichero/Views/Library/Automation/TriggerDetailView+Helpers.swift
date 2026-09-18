import OSLog
import SwiftUI

extension TriggerDetailView {

    // MARK: - Helpers

    var statusColor: Color {
        switch trigger.status {
        case "active": return .green
        case "paused": return .yellow
        case "error": return .red
        default: return .secondary
        }
    }

    var triggerStatus: Status {
        switch trigger.status {
        case "active": return .completed
        case "paused": return .pending
        case "error": return .failed
        default: return .pending
        }
    }

    // `executionStatusColor`/`loadExecutions` MOVED to
    // `TriggerRunHistoryView.swift` (#4705 "4b-2").

    // MARK: - Actions

    func pauseTrigger() async {
        do {
            let service = AutomationService(apiClient: apiClient)
            _ = try await service.pauseTrigger(triggerId: trigger.triggerId)
        } catch {
            triggerDetailLogger.error("Failed to pause trigger: \(error.localizedDescription)")
        }
    }

    func resumeTrigger() async {
        do {
            let service = AutomationService(apiClient: apiClient)
            _ = try await service.resumeTrigger(triggerId: trigger.triggerId)
        } catch {
            triggerDetailLogger.error("Failed to resume trigger: \(error.localizedDescription)")
        }
    }
}
