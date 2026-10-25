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
            throw await ActivityServiceError.failure(statusCode: statusCode, payload: payload)
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
            throw await ActivityServiceError.failure(statusCode: statusCode, payload: payload)
        }
    }

    /// One recipe run's status (`GET /api/recipes/project/runs/{job_id}`): its folders done of its
    /// folders in all (`activity.run.progress-per-folder`, #5540). nil for a job that is not a recipe run.
    func getRecipeRunStatus(jobId: String) async throws -> Components.Schemas.RecipeRunStatus? {
        switch try await client.api.recipeRunStatusApiRecipesProjectRunsJobIdGet(path: .init(jobId: jobId)) {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent:
            return nil
        case .undocumented(let statusCode, let payload):
            if statusCode == 404 { return nil }
            throw await ActivityServiceError.failure(statusCode: statusCode, payload: payload)
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
                mode: ActivityMode(engine: body.mode?.rawValue),
                machine: body.machine,
                activity: body.activity
            )
        case .undocumented(let statusCode, let payload):
            // A refusal keeps the engine's typed body (#5469): the footer names
            // WHY (the project's location vs the app's credentials).
            throw await ActivityServiceError.failure(statusCode: statusCode, payload: payload)
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

// MARK: - Error Types

enum ActivityServiceError: LocalizedError {
    case validationError(String)
    case badRequest(String)
    case unexpectedResponse(Int)
    /// The engine said no, in its own words (a 409 refusal): shown as it is.
    case refused(String)

    /// What an undocumented answer means, from ONE read of its body (a body streams once): an access denial
    /// (#5431), else the engine's own words (`{"detail": "The project is busy"}`) as `.refused`, else the status.
    static func failure(statusCode: Int, payload: UndocumentedPayload) async -> Error {
        let body = await AccessError.collectDenialBody(payload)
        if let denial = AccessError.classify(statusCode: statusCode, body: body) { return denial }
        if let words = EngineErrorDetail.message(from: body) { return refused(words) }
        return unexpectedResponse(statusCode)
    }

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
