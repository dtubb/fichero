import FicheroAPIClient
import Foundation

// MARK: - Episode ledger reads (#22 / workflows-done-right per-node inspection)

/// One recorded model call under a workflow run: the node that made it, the
/// FULL exchange, model identity, subject, and timing. The engine's episode
/// ledger is append-only JSONL; this is its read model for the trace surface.
struct WorkflowEpisode: Identifiable {
    let id: String
    let recordedAt: String?
    let kind: String
    /// The graph node id this call ran under — matches `RunTraceNode.id`.
    let nodeId: String?
    let tool: String?
    let provider: String?
    let model: String?
    let useCase: String?
    let system: String?
    let prompt: String?
    let output: String?
    let thinking: String?
    let subjectText: String?
    let durationMs: Int?

    init?(raw: [String: (any Sendable)?]) {
        guard let episodeId = raw["episode_id"] as? String else { return nil }
        id = episodeId
        recordedAt = raw["at"] as? String
        kind = raw["kind"] as? String ?? "model_call"
        let run = raw["run"] as? [String: (any Sendable)?] ?? [:]
        nodeId = run["node_id"] as? String
        tool = run["node"] as? String
        let model = raw["model"] as? [String: (any Sendable)?] ?? [:]
        provider = model["provider"] as? String
        self.model = model["model"] as? String
        useCase = model["use_case"] as? String
        let exchange = raw["exchange"] as? [String: (any Sendable)?] ?? [:]
        system = exchange["system"] as? String
        prompt = exchange["prompt"] as? String
        output = exchange["output"] as? String
        thinking = exchange["thinking"] as? String
        let subject = raw["subject"] as? [String: (any Sendable)?] ?? [:]
        subjectText = (subject["document_name"] as? String)
            ?? (subject["file"] as? String)
            ?? (subject["document_id"] as? String)
        let timing = raw["timing"] as? [String: (any Sendable)?] ?? [:]
        if let millis = timing["duration_ms"] as? Int {
            durationMs = millis
        } else if let millis = timing["duration_ms"] as? Double {
            durationMs = Int(millis)
        } else {
            durationMs = nil
        }
    }

    var modelText: String? {
        switch (provider, model) {
        case let (provider?, model?): "\(provider)/\(model)"
        case let (nil, model?): model
        case let (provider?, nil): provider
        default: nil
        }
    }
}

extension ActivityService {
    /// GET /api/workflow-execution/threads/{id}/episodes — the per-node
    /// "what did the model actually see and say" record for a run.
    func getThreadEpisodes(threadId: String) async throws -> [WorkflowEpisode] {
        let response = try await client.api
            .getThreadEpisodesApiWorkflowExecutionThreadsThreadIdEpisodesGet(
                path: .init(threadId: threadId)
            )
        switch response {
        case .ok(let okResponse):
            let payload = try okResponse.body.json.additionalProperties.value
            let rawEpisodes = payload["episodes"] as? [(any Sendable)?] ?? []
            return rawEpisodes.compactMap { entry in
                (entry as? [String: (any Sendable)?]).flatMap(WorkflowEpisode.init)
            }
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ActivityServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ActivityServiceError.unexpectedResponse(statusCode)
        }
    }
}
