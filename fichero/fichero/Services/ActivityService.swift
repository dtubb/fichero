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
        let ficheroClient = FicheroClient(
            baseURL: EngineConfig.host,
            libraryPath: libraryPath,
            transportMode: EngineConfig.transportMode
        )
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

    // MARK: - Workflow runs (#4960: ONE SOURCE — the runs table, not the event log)

    /// List runs straight from the engine's `workflow_runs` table — the SAME
    /// record `/activity/jobs` (the popover) already reads, so the Activity
    /// window/browser agree with it instead of a lossy 7-day/100-event log
    /// (the review's verified cause of the two surfaces disagreeing).
    /// `status` filters server-side; omit for every non-deleted run, newest
    /// first. Paged so a caller can page in further rows.
    func listWorkflowRuns(
        status: [String]? = nil,
        limit: Int = 50,
        offset: Int = 0
    ) async throws -> Components.Schemas.WorkflowRunListResponse {
        let response = try await client.api.listWorkflowRunsRouteApiWorkflowExecutionRunsGet(
            query: .init(status: status, limit: limit, offset: offset),
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ActivityServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, let payload):
            // A 401/403 is the engine refusing the app's credentials (#5431: an
            // engine respawn's token change); typed, so the window can say so.
            if let denial = await AccessError.denial(statusCode: statusCode, payload: payload) {
                throw denial
            }
            throw ActivityServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Bulk-delete runs by explicit id OR by a status filter — "Clear
    /// Failed" is this SAME call with `statuses: ["failed"]`. The ONE delete
    /// every surface (popover, window, browser) routes through (#4960).
    /// `skippedIds` names ids requested but not removed — never a silent no-op.
    func deleteWorkflowRuns(
        threadIds: [String]? = nil,
        statuses: [String]? = nil
    ) async throws -> Components.Schemas.WorkflowRunDeleteResult {
        let response = try await client.api.deleteWorkflowRunsRouteApiWorkflowExecutionRunsDeletePost(
            body: .json(.init(threadIds: threadIds, statuses: statuses)),
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ActivityServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ActivityServiceError.unexpectedResponse(statusCode)
        }
    }

    // MARK: - Recipe runs (#5576)

    /// The project's recipe runs, newest first (`GET /api/recipes/project/runs`):
    /// what the project window's strip comes back to after a relaunch.
    func getProjectRecipeRuns() async throws -> [Components.Schemas.RecipeRunStatus] {
        switch try await client.api.recipeRunsApiRecipesProjectRunsGet() {
        case .ok(let okResponse):
            return try okResponse.body.json.items
        case .undocumented(let statusCode, let payload):
            if let denial = await AccessError.denial(statusCode: statusCode, payload: payload) {
                throw denial
            }
            throw ActivityServiceError.unexpectedResponse(statusCode)
        }
    }

    // MARK: - Background jobs (#user-machine-always-useful FIX 2)

    /// Snapshot of currently-running background jobs + rough process CPU%.
    ///
    /// Global (process-wide), read-only and cheap — the single source both the
    /// toolbar Activity popover and the full Activity viewer read so they can't
    /// disagree about what is running. No filters, so the only outcomes are a
    /// value or a transport/HTTP failure the caller decides how to surface.
    func getBackgroundJobs() async throws -> BackgroundJobsSnapshot {
        let response = try await client.api.listBackgroundJobsApiActivityJobsGet()

        switch response {
        case .ok(let okResponse):
            let body = try okResponse.body.json
            return BackgroundJobsSnapshot(
                jobs: (body.jobs ?? []).map { ActivityJob($0) },
                processCpuPercent: body.processCpuPercent,
                cpuCount: body.cpuCount,
                paused: body.paused ?? false,
                machine: body.machine
            )
        case .undocumented(let statusCode, let payload):
            // A refusal keeps the engine's typed body (#5469): the footer names
            // WHY (the project's location vs the app's credentials).
            if let denial = await AccessError.denial(statusCode: statusCode, payload: payload) {
                throw denial
            }
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
}

// MARK: - Error Types

enum ActivityServiceError: LocalizedError {
    case validationError(String)
    case badRequest(String)
    case unexpectedResponse(Int)
    /// The engine said no, in its own words (a 409 refusal): shown as it is.
    case refused(String)

    var errorDescription: String? {
        switch self {
        case .refused(let words):
            return words
        case .validationError(let message):
            return "Validation error: \(message)"
        case .badRequest(let message):
            return "Bad request: \(message)"
        case .unexpectedResponse(let statusCode):
            return "Unexpected response: HTTP \(statusCode)"
        }
    }
}

// MARK: - One job and everything under it (#5353, #5415)

extension ActivityService {
    /// `GET /api/activity/jobs/{id}`: a run (its id is its thread id), its
    /// steps and their pages, with time, cost and errors rolled up. `nil` when
    /// the project has no job by that id: a run recorded before the jobs
    /// table existed has no tree, and the window shows its run row alone.
    func getJobTree(id: String) async throws -> ActivityJobNode? {
        let response = try await client.api.getJobTreeApiActivityJobsJobIdGet(path: .init(jobId: id))
        switch response {
        case .ok(let okResponse):
            return ActivityJobNode(try okResponse.body.json)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ActivityServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, let payload):
            if statusCode == 404 { return nil }
            if let denial = await AccessError.denial(statusCode: statusCode, payload: payload) {
                throw denial
            }
            throw ActivityServiceError.unexpectedResponse(statusCode)
        }
    }

    /// `GET /api/activity/jobs/{id}/log` (#5561): the lines the engine wrote
    /// for this row and the rows under it, newest last. `nil` when the project
    /// has no job by that id (a job of its own the job table has no row for).
    func getJobLog(id: String) async throws -> [ActivityJobLogLine]? {
        let response = try await client.api.getJobLogApiActivityJobsJobIdLogGet(path: .init(jobId: id))
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.lines?.enumerated().map { ActivityJobLogLine(index: $0.offset, $0.element) } ?? []
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ActivityServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, let payload):
            if statusCode == 404 { return nil }
            if let denial = await AccessError.denial(statusCode: statusCode, payload: payload) {
                throw denial
            }
            throw ActivityServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Pause or resume one job and what is under it (`activity.pause.per-job`):
    /// the audited `job.pause` action. Returns the job's state after the request.
    func setJobPaused(id: String, paused: Bool) async throws -> String {
        let response = try await client.api.setJobPausedApiActivityJobsJobIdPausedPut(
            path: .init(jobId: id),
            body: .json(.init(paused: paused))
        )
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.state
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ActivityServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ActivityServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Stop one job and what is under it (the audited `job.cancel` action).
    /// Returns the job's state after the request.
    /// Read the pages a finished run did not do (#5555, the account's offer):
    /// one new run of the same workflow and model over those pages only.
    /// Returns the new run's thread id.
    func readPagesAgain(threadId: String) async throws -> String {
        let response = try await client.api.readPagesAgainApiWorkflowExecutionThreadsThreadIdReadAgainPost(
            path: .init(threadId: threadId)
        )
        switch response {
        case .accepted(let accepted):
            return try accepted.body.json.threadId
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ActivityServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, let payload):
            if let denial = await AccessError.denial(statusCode: statusCode, payload: payload) {
                throw denial
            }
            throw ActivityServiceError.unexpectedResponse(statusCode)
        }
    }

    func cancelJob(id: String) async throws -> String {
        let response = try await client.api.cancelJobApiActivityJobsJobIdCancelPost(path: .init(jobId: id))
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.state
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ActivityServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ActivityServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Run a failed or stopped job again (the audited `job.retry`, #5356): it
    /// goes back to waiting and carries on from its own checkpoint. Returns the
    /// job's state after the request. A refusal (409: work a run hands in, a
    /// training on Hugging Face, work already waiting) throws the engine's words.
    func retryJob(id: String) async throws -> String {
        let response = try await client.api.retryJobApiActivityJobsJobIdRetryPost(path: .init(jobId: id))
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.state
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ActivityServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, let payload):
            // One read of the body serves both: a streamed body reads only once.
            let body = await AccessError.collectDenialBody(payload)
            if let denial = AccessError.classify(statusCode: statusCode, body: body) {
                throw denial
            }
            if let words = EngineErrorDetail.message(from: body) {
                throw ActivityServiceError.refused(words)
            }
            throw ActivityServiceError.unexpectedResponse(statusCode)
        }
    }
}
