import FicheroAPIClient
import Foundation
import OpenAPIRuntime

// Split out of ActivityService.swift by file_length (#6101); behaviour unchanged.

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
            throw await ActivityServiceError.failure(statusCode: statusCode, payload: payload)
        }
    }

    /// `GET /api/activity/jobs/{id}/log` (#5561): the lines the engine wrote
    /// for this row and the rows under it, newest last. `nil` when the project
    /// has no job by that id (a job of its own the job table has no row for).
    func getJobLog(id: String, developer: Bool = false, problemsOnly: Bool = false) async throws -> [ActivityJobLogLine]? {
        // The person's log by default; the Developer level adds the debug lines (`activity.log.developer-level`).
        let response = try await client.api.getJobLogApiActivityJobsJobIdLogGet(
            path: .init(jobId: id),
            query: .init(detail: developer ? .developer : .person, level: problemsOnly ? .problems : .all))
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.lines?.enumerated().map { ActivityJobLogLine(index: $0.offset, $0.element) } ?? []
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ActivityServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, let payload):
            if statusCode == 404 { return nil }
            throw await ActivityServiceError.failure(statusCode: statusCode, payload: payload)
        }
    }

    /// The jobs queued behind one kind's row, in the order the lane picks them (`activity.window.expands-to-pages`,
    /// #5839). Nil when the engine has no such kind row.
    func listQueuedItems(kind: String, limit: Int = 50, offset: Int = 0) async throws -> [ActivityQueuedItem] {
        let response = try await client.api.listQueuedItemsApiActivityJobsKindKindItemsGet(
            path: .init(kind: kind), query: .init(limit: limit, offset: offset))
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items.map(ActivityQueuedItem.init)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ActivityServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, let payload):
            throw await ActivityServiceError.failure(statusCode: statusCode, payload: payload)
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
            throw await ActivityServiceError.failure(statusCode: statusCode, payload: payload)
        }
    }

    /// Set how background work runs on this Mac (`activity.mode.start-stop`,
    /// #5621): the audited `background.mode` action behind the Start / Stop
    /// control. Returns the mode the engine now has.
    func setBackgroundMode(_ mode: ActivityMode) async throws -> ActivityMode {
        let payload: Components.Schemas.BackgroundModeRequest.ModePayload
        switch mode {
        case .automatic: payload = .automatic
        case .started: payload = .started
        case .paused: payload = .paused
        }
        let response = try await client.api.setBackgroundModeApiActivityJobsModePut(
            body: .json(.init(mode: payload))
        )
        switch response {
        case .ok(let okResponse):
            return ActivityMode(engine: try okResponse.body.json.mode.rawValue)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ActivityServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, let payload):
            throw await ActivityServiceError.failure(statusCode: statusCode, payload: payload)
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

    /// Clear Failed for jobs (the audited `job.clear_failed`, #5634): every
    /// failed job the jobs read lists is kept and no longer listed. Returns
    /// the ids cleared. Failed workflow runs are `deleteWorkflowRuns(statuses:)`.
    func clearFailedJobs() async throws -> [String] {
        let response = try await client.api.clearFailedJobsApiActivityJobsClearFailedPost()
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.clearedIds
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ActivityServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, let payload):
            throw await ActivityServiceError.failure(statusCode: statusCode, payload: payload)
        }
    }

    /// Run a failed or stopped job again (the audited `job.retry`, #5356): it
    /// goes back to waiting and carries on from its own checkpoint. Returns the
    /// job's state after the request. A refusal (409: work a run hands in, a
    /// training on Hugging Face, work already waiting) throws the engine's words.
    /// What a retry answered: the job's state, and for a retried workflow run, the NEW run's id and the run it
    /// replaces (`replaces`), which is no longer listed.
    struct RetryAnswer: Equatable {
        let id: String
        let state: String
        let replaces: String?
    }

    func retryJob(id: String) async throws -> RetryAnswer {
        let response = try await client.api.retryJobApiActivityJobsJobIdRetryPost(path: .init(jobId: id))
        switch response {
        case .ok(let okResponse):
            let answer = try okResponse.body.json
            return RetryAnswer(id: answer.id, state: answer.state, replaces: answer.replaces)
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

    /// A step takes a candidate of its chain as the project's reader (#5352): the engine sets it, keeps it as the
    /// project's override and saves the recipe, as Set Up's Use for This Step does.
    func useCandidate(step: String, card: String) async throws {
        let response = try await client.api.useCandidateForStepApiRecipesProjectStepsUseCandidatePost(
            body: .json(.init(step: step, card: card)))
        switch response {
        case .ok:
            return
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ActivityServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, let payload):
            let body = await AccessError.collectDenialBody(payload)
            if let denial = AccessError.classify(statusCode: statusCode, body: body) { throw denial }
            if let words = EngineErrorDetail.message(from: body) { throw ActivityServiceError.refused(words) }
            throw ActivityServiceError.unexpectedResponse(statusCode)
        }
    }
}
