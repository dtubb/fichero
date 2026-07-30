import FicheroAPIClient
import Foundation
import OpenAPIRuntime
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ActivityService")

/// Service for interacting with the Activity API using generated OpenAPI client
@MainActor
class ActivityService {
    let client: FicheroClient

    /// Initialize with FicheroClient (preferred - non-throwing)
    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    /// Convenience initializer from APIClient - extracts library path
    convenience init(apiClient: APIClient) {
        let libraryPath = apiClient.currentLibraryPath ?? ""
        let ficheroClient = FicheroClient(baseURL: EngineConfig.host, libraryPath: libraryPath, transportMode: EngineConfig.transportMode)
        self.init(ficheroClient: ficheroClient)
    }

    // MARK: - Activity Queries

    /// Fetch recent activities
    func getRecentActivities(limit: Int = 50) async throws -> [ActivityItem] {
        let response = try await client.api.getRecentActivitiesApiActivityRecentGet(
            query: .init(limit: limit),
        )

        switch response {
        case .ok(let okResponse):
            let envelope = try okResponse.body.json
            return envelope.items.map { convertToActivityItem($0) }
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ActivityServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ActivityServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Query activities with filters
    func queryActivities(
        types: [String]? = nil,
        levels: [String]? = nil,
        workflowId: String? = nil,
        threadId: String? = nil,
        batchId: String? = nil,
        since: Date? = nil,
        until: Date? = nil,
        search: String? = nil,
        limit: Int = 100,
        offset: Int = 0
    ) async throws -> [ActivityItem] {
        let response = try await client.api.listActivitiesApiActivityGet(
            query: .init(
                types: types?.joined(separator: ","),
                levels: levels?.joined(separator: ","),
                workflowId: workflowId,
                batchId: batchId,
                threadId: threadId,
                since: since.map { ISO8601DateFormatter().string(from: $0) },
                until: until.map { ISO8601DateFormatter().string(from: $0) },
                search: search,
                limit: limit,
                offset: offset
            ),
        )

        switch response {
        case .ok(let okResponse):
            let envelope = try okResponse.body.json
            return envelope.items.map { convertToActivityItem($0) }
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ActivityServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ActivityServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Get activities for a specific thread (run)
    func getThreadActivities(threadId: String, limit: Int = 500) async throws -> [ActivityItem] {
        return try await queryActivities(threadId: threadId, limit: limit)
    }

    /// Get activity statistics
    func getActivityStats(hours: Int = 24) async throws -> ActivityStats {
        let response = try await client.api.getActivityStatsApiActivityStatsGet(
            query: .init(hours: hours),
        )

        switch response {
        case .ok(let okResponse):
            let stats = try okResponse.body.json
            return convertToActivityStats(stats)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ActivityServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ActivityServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Get activities for a specific workflow
    func getWorkflowActivities(workflowId: String, limit: Int = 100) async throws -> [ActivityItem] {
        let response = try await client.api.getWorkflowActivityApiActivityWorkflowWorkflowIdGet(
            path: .init(workflowId: workflowId),
            query: .init(limit: limit),
        )

        switch response {
        case .ok(let okResponse):
            let envelope = try okResponse.body.json
            return envelope.items.map { convertToActivityItem($0) }
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ActivityServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ActivityServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Get activities for a specific batch
    func getBatchActivities(batchId: String, limit: Int = 100) async throws -> [ActivityItem] {
        let response = try await client.api.getBatchActivityApiActivityBatchBatchIdGet(
            path: .init(batchId: batchId),
            query: .init(limit: limit),
        )

        switch response {
        case .ok(let okResponse):
            let envelope = try okResponse.body.json
            return envelope.items.map { convertToActivityItem($0) }
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ActivityServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ActivityServiceError.unexpectedResponse(statusCode)
        }
    }

    // MARK: - Workflow Execution History

    /// Get checkpoint history for a workflow thread (state at each step)
    func getCheckpointHistory(threadId: String, limit: Int = 100) async throws -> CheckpointHistoryResponse {
        let response = try await client.api.getThreadHistoryApiWorkflowExecutionThreadsThreadIdHistoryGet(
            path: .init(threadId: threadId),
            query: .init(limit: limit),
        )

        switch response {
        case .ok(let okResponse):
            let history = try okResponse.body.json
            return convertToCheckpointHistory(history, threadId: threadId)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ActivityServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ActivityServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Get workflow run data including Python code and execution log
    func getWorkflowRun(threadId: String) async throws -> WorkflowRunResponse {
        let response = try await client.api.getWorkflowRunApiWorkflowExecutionThreadsThreadIdRunGet(
            path: .init(threadId: threadId),
        )

        switch response {
        case .ok(let okResponse):
            let run = try okResponse.body.json
            return convertToWorkflowRun(run)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ActivityServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ActivityServiceError.unexpectedResponse(statusCode)
        }
    }

    // MARK: - Cleanup

    /// Cleanup old activities
    func cleanupOldActivities(days: Int = 30) async throws -> Int {
        let response = try await client.api.cleanupOldActivitiesApiActivityCleanupDelete(
            query: .init(days: days),
        )

        switch response {
        case .ok(let okResponse):
            let result = try okResponse.body.json
            return result.deleted
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ActivityServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ActivityServiceError.unexpectedResponse(statusCode)
        }
    }

}

// MARK: - Type Conversions

extension ActivityService {
    /// Convert generated ActivityResponse to app ActivityItem
    func convertToActivityItem(_ response: Components.Schemas.ActivityResponse) -> ActivityItem {
        // Convert metadata from OpenAPIObjectContainer to [String: AnyValueAsString]
        var metadata: [String: AnyValueAsString]?
        if let metadataPayload = response.metadata {
            var converted: [String: AnyValueAsString] = [:]
            for (key, value) in metadataPayload.additionalProperties.value {
                // Convert any value to string representation
                let stringValue: String
                if let str = value as? String {
                    stringValue = str
                } else if let bool = value as? Bool {
                    // #4024: Bool BEFORE NSNumber — a bridged Bool IS an NSNumber
                    // (__NSCFBoolean), so testing NSNumber first rendered `true` as "1".
                    stringValue = String(bool)
                } else if let num = value as? NSNumber {
                    stringValue = num.stringValue
                } else {
                    stringValue = String(describing: value)
                }
                converted[key] = AnyValueAsString(stringValue)
            }
            metadata = converted.isEmpty ? nil : converted
        }

        return ActivityItem(
            id: response.id,
            type: response._type,
            level: response.level,
            timestamp: response.timestamp,
            message: response.message,
            workflowId: response.workflowId,
            batchId: response.batchId,
            threadId: response.threadId,
            nodeId: response.nodeId,
            metadataRaw: metadata,
            durationMs: response.durationMs,
            error: response.error
        )
    }

    /// Convert generated ActivityStatsResponse to app ActivityStats
    func convertToActivityStats(_ response: Components.Schemas.ActivityStatsResponse) -> ActivityStats {
        ActivityStats(
            totalActivities: response.totalActivities,
            activitiesByType: response.activitiesByType.additionalProperties,
            activitiesByLevel: response.activitiesByLevel.additionalProperties,
            errorCount: response.errorCount,
            warningCount: response.warningCount,
            avgWorkflowDurationMs: response.avgWorkflowDurationMs,
            successRate: response.successRate,
            periodStart: response.periodStart,
            periodEnd: response.periodEnd
        )
    }

    /// Convert generated checkpoint history to app type
    func convertToCheckpointHistory(
        _ response: Components.Schemas.CheckpointHistoryResponse,
        threadId: String
    ) -> CheckpointHistoryResponse {
        let checkpoints = response.checkpoints.map { checkpoint -> CheckpointSnapshot in
            // Convert state values
            var stateValues: [String: CheckpointValue] = [:]
            if let values = checkpoint.stateValues {
                for (key, value) in values.additionalProperties.value {
                    stateValues[key] = CheckpointValue(value as Any)
                }
            }

            // Convert writes
            var writes: [String: CheckpointValue] = [:]
            if let writeValues = checkpoint.writes {
                for (key, value) in writeValues.additionalProperties.value {
                    writes[key] = CheckpointValue(value as Any)
                }
            }

            return CheckpointSnapshot(
                checkpointId: checkpoint.checkpointId,
                parentCheckpointId: checkpoint.parentCheckpointId,
                step: checkpoint.step,
                timestamp: checkpoint.timestamp,
                nodeName: checkpoint.nodeName,
                stateValues: stateValues,
                writes: writes,
                nextNodes: checkpoint.nextNodes ?? []
            )
        }

        return CheckpointHistoryResponse(
            threadId: response.threadId,
            workflowId: response.workflowId,
            workflowName: response.workflowName,
            totalSteps: response.totalSteps,
            checkpoints: checkpoints
        )
    }

    /// Convert generated workflow run to app type
    func convertToWorkflowRun(_ response: Components.Schemas.WorkflowRunResponse) -> WorkflowRunResponse {
        // Extract workflow snapshot from OpenAPI Payload wrapper
        let workflowSnapshot: [String: Any]? = response.workflowSnapshot?.additionalProperties.value as? [String: Any]

        // Extract node name map from OpenAPI Payload wrapper
        let nodeNameMap: [String: String]? = response.nodeNameMap?.additionalProperties

        // Extract progress timeline from OpenAPI Payload wrapper
        let progressTimeline: [String: Any]? = response.progressTimeline?.additionalProperties.value as? [String: Any]

        return WorkflowRunResponse(
            threadId: response.threadId,
            workflowId: response.workflowId,
            workflowName: response.workflowName,
            pythonCode: response.pythonCode,
            executionLog: response.executionLog,
            status: response.status.rawValue,
            startedAt: response.startedAt,
            completedAt: response.completedAt,
            durationMs: response.durationMs,
            error: response.error,
            workflowSnapshot: workflowSnapshot,
            nodeNameMap: nodeNameMap,
            progressTimeline: progressTimeline,
            diagramMermaid: response.diagramMermaid,
            runArtifacts: (response.runArtifacts ?? []).map { artifact in
                WorkflowRunArtifact(
                    artifactId: artifact.artifactId,
                    artifactType: artifact.artifactType,
                    documentId: artifact.documentId,
                    documentName: artifact.documentName,
                    sourceDocumentId: artifact.sourceDocumentId,
                    sourceDocumentName: artifact.sourceDocumentName,
                    runId: artifact.runId,
                    stepName: artifact.stepName,
                    nodeName: artifact.nodeName,
                    sequence: artifact.sequence,
                    createdAt: artifact.createdAt
                )
            }
        )
    }
}

// MARK: - Error Types

enum ActivityServiceError: LocalizedError {
    case validationError(String)
    case badRequest(String)
    case unexpectedResponse(Int)

    var errorDescription: String? {
        switch self {
        case .validationError(let message):
            return "Validation error: \(message)"
        case .badRequest(let message):
            return "Bad request: \(message)"
        case .unexpectedResponse(let statusCode):
            return "Unexpected response: HTTP \(statusCode)"
        }
    }
}
