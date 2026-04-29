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

    func executionStatusColor(_ status: String) -> Color {
        switch status {
        case "completed": return .green
        case "running": return .blue
        case "failed": return .red
        default: return .secondary
        }
    }

    // MARK: - Actions

    func loadExecutions() async {
        isLoading = true
        error = nil

        do {
            let service = AutomationService(apiClient: apiClient)
            executions = try await service.getTriggerExecutions(triggerId: trigger.triggerId, limit: 20)
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

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
