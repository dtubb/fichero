import FicheroAPIClient
import Foundation

// Maps between the generated OpenAPI automation schemas (typed after #3131) and
// the app-facing automation models used across the sidebar/detail views (#3030).
// Keeping the app models means the ~20 view/model call sites are untouched; only
// AutomationService's transport swaps to the generated, typed operations.

// MARK: - Schedules

extension ScheduleInfo {
    init(response: Components.Schemas.ScheduleResponse) {
        self.init(
            scheduleId: response.scheduleId,
            name: response.name,
            workflowId: response.workflowId,
            scheduleType: response.scheduleType,
            cronExpression: response.cronExpression,
            intervalSeconds: response.intervalSeconds,
            runAt: response.runAt,
            timezone: response.timezone,
            status: response.status,
            inputs: response.inputs.additionalProperties,
            useBatch: response.useBatch,
            batchItems: response.batchItems.map { $0.additionalProperties },
            maxConcurrent: response.maxConcurrent,
            createdAt: response.createdAt,
            updatedAt: response.updatedAt,
            lastRunAt: response.lastRunAt,
            nextRunAt: response.nextRunAt,
            runCount: response.runCount,
            errorMessage: response.errorMessage
        )
    }
}

extension ScheduleRunInfo {
    init(response: Components.Schemas.ScheduleRunResponse) {
        self.init(
            runId: response.runId,
            scheduleId: response.scheduleId,
            startedAt: response.startedAt,
            completedAt: response.completedAt,
            status: response.status,
            batchId: response.batchId,
            error: response.error
        )
    }
}

extension Components.Schemas.CreateScheduleRequest {
    init(app request: CreateScheduleRequest) {
        self.init(
            name: request.name,
            workflowId: request.workflowId,
            config: .init(
                scheduleType: request.config.scheduleType,
                cronExpression: request.config.cronExpression,
                intervalSeconds: request.config.intervalSeconds,
                runAt: request.config.runAt,
                timezone: request.config.timezone,
                startDate: request.config.startDate,
                endDate: request.config.endDate,
                maxRuns: request.config.maxRuns
            ),
            inputs: .init(additionalProperties: request.inputs),
            useBatch: request.useBatch,
            batchItems: request.batchItems.map { .init(additionalProperties: $0) },
            maxConcurrent: request.maxConcurrent
        )
    }
}

// MARK: - Triggers

extension TriggerInfo {
    init(response: Components.Schemas.TriggerResponse) {
        self.init(
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
            inputsTemplate: response.inputsTemplate.additionalProperties,
            status: response.status,
            useBatch: response.useBatch,
            maxConcurrent: response.maxConcurrent,
            createdAt: response.createdAt,
            updatedAt: response.updatedAt,
            lastTriggeredAt: response.lastTriggeredAt,
            triggerCount: response.triggerCount,
            errorMessage: response.errorMessage
        )
    }
}

extension TriggerExecutionInfo {
    init(response: Components.Schemas.TriggerExecutionResponse) {
        self.init(
            executionId: response.executionId,
            triggerId: response.triggerId,
            triggeredAt: response.triggeredAt,
            filePaths: response.filePaths,
            batchId: response.batchId,
            status: response.status,
            error: response.error,
            completedAt: response.completedAt
        )
    }
}

extension Components.Schemas.CreateTriggerRequest {
    init(app request: CreateTriggerRequest) {
        self.init(
            name: request.name,
            workflowId: request.workflowId,
            config: .init(
                watchPath: request.config.watchPath,
                recursive: request.config.recursive,
                events: request.config.events,
                filterMode: request.config.filterMode,
                filterPattern: request.config.filterPattern,
                filterExtensions: request.config.filterExtensions,
                excludePatterns: request.config.excludePatterns,
                debounceSeconds: request.config.debounceSeconds,
                batchDelaySeconds: request.config.batchDelaySeconds
            ),
            inputsTemplate: .init(additionalProperties: request.inputsTemplate),
            useBatch: request.useBatch,
            maxConcurrent: request.maxConcurrent
        )
    }
}
