import Foundation

// MARK: - Workflow Run Response

/// Response with workflow run data (code, logs, etc.)
struct WorkflowRunResponse: Codable {
    let threadId: String
    let workflowId: String
    let workflowName: String
    let pythonCode: String?
    let executionLog: String?
    let status: String
    let startedAt: String?
    let completedAt: String?
    let durationMs: Double?
    let error: String?
    let workflowSnapshot: [String: Any]?
    let nodeNameMap: [String: String]?
    let progressTimeline: [String: Any]?
    let diagramMermaid: String?
    /// Artifacts produced by this run, in pipeline order (#4313). Empty for
    /// legacy runs recorded before artifact provenance existed.
    let runArtifacts: [WorkflowRunArtifact]
    /// One record per PLANNED step (#4284). Authoritative for per-step status:
    /// the timeline can only report the steps that emitted an entry, so a step
    /// missing from it is ambiguous between "never ran" and "ran silently".
    /// Empty for legacy runs recorded before step records existed, which is
    /// why the timeline mapping is kept as the fallback rather than deleted.
    let steps: [WorkflowRunStep]
    /// What the run SPENT (2026-09-03). Nil for a run that made no model
    /// call, or one recorded before usage accounting existed — which is not
    /// the same as a run that cost nothing, so nil renders as nothing at all
    /// rather than as "$0.00".
    let runUsage: RunUsage?

    enum CodingKeys: String, CodingKey {
        case threadId = "thread_id"
        case workflowId = "workflow_id"
        case workflowName = "workflow_name"
        case pythonCode = "python_code"
        case executionLog = "execution_log"
        case status
        case startedAt = "started_at"
        case completedAt = "completed_at"
        case durationMs = "duration_ms"
        case error
        case workflowSnapshot = "workflow_snapshot"
        case nodeNameMap = "node_name_map"
        case progressTimeline = "progress_timeline"
        case diagramMermaid = "diagram_mermaid"
        case runArtifacts = "run_artifacts"
        case steps
        case runUsage = "run_usage"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        threadId = try container.decode(String.self, forKey: .threadId)
        workflowId = try container.decode(String.self, forKey: .workflowId)
        workflowName = try container.decode(String.self, forKey: .workflowName)
        pythonCode = try container.decodeIfPresent(String.self, forKey: .pythonCode)
        executionLog = try container.decodeIfPresent(String.self, forKey: .executionLog)
        status = try container.decode(String.self, forKey: .status)
        startedAt = try container.decodeIfPresent(String.self, forKey: .startedAt)
        completedAt = try container.decodeIfPresent(String.self, forKey: .completedAt)
        durationMs = try container.decodeIfPresent(Double.self, forKey: .durationMs)
        error = try container.decodeIfPresent(String.self, forKey: .error)

        // Decode JSON fields using CheckpointValue for type erasure
        if let snapshotData = try? container.decodeIfPresent(CheckpointValue.self, forKey: .workflowSnapshot) {
            workflowSnapshot = snapshotData.value as? [String: Any]
        } else {
            workflowSnapshot = nil
        }

        nodeNameMap = try container.decodeIfPresent([String: String].self, forKey: .nodeNameMap)

        if let timelineData = try? container.decodeIfPresent(CheckpointValue.self, forKey: .progressTimeline) {
            progressTimeline = timelineData.value as? [String: Any]
        } else {
            progressTimeline = nil
        }

        diagramMermaid = try container.decodeIfPresent(String.self, forKey: .diagramMermaid)
        runArtifacts = try container.decodeIfPresent(
            [WorkflowRunArtifact].self, forKey: .runArtifacts
        ) ?? []
        steps = try container.decodeIfPresent(
            [WorkflowRunStep].self, forKey: .steps
        ) ?? []
        runUsage = try container.decodeIfPresent(RunUsage.self, forKey: .runUsage)
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(threadId, forKey: .threadId)
        try container.encode(workflowId, forKey: .workflowId)
        try container.encode(workflowName, forKey: .workflowName)
        try container.encodeIfPresent(pythonCode, forKey: .pythonCode)
        try container.encodeIfPresent(executionLog, forKey: .executionLog)
        try container.encode(status, forKey: .status)
        try container.encodeIfPresent(startedAt, forKey: .startedAt)
        try container.encodeIfPresent(completedAt, forKey: .completedAt)
        try container.encodeIfPresent(durationMs, forKey: .durationMs)
        try container.encodeIfPresent(error, forKey: .error)

        if let workflowSnapshot = workflowSnapshot {
            try container.encode(CheckpointValue(workflowSnapshot), forKey: .workflowSnapshot)
        }
        try container.encodeIfPresent(nodeNameMap, forKey: .nodeNameMap)
        if let progressTimeline = progressTimeline {
            try container.encode(CheckpointValue(progressTimeline), forKey: .progressTimeline)
        }
        try container.encodeIfPresent(diagramMermaid, forKey: .diagramMermaid)
        try container.encode(runArtifacts, forKey: .runArtifacts)
        try container.encode(steps, forKey: .steps)
        try container.encodeIfPresent(runUsage, forKey: .runUsage)
    }

    init(
        threadId: String,
        workflowId: String,
        workflowName: String,
        pythonCode: String?,
        executionLog: String?,
        status: String,
        startedAt: String?,
        completedAt: String?,
        durationMs: Double?,
        error: String?,
        workflowSnapshot: [String: Any]? = nil,
        nodeNameMap: [String: String]? = nil,
        progressTimeline: [String: Any]? = nil,
        diagramMermaid: String? = nil,
        runArtifacts: [WorkflowRunArtifact] = [],
        steps: [WorkflowRunStep] = [],
        runUsage: RunUsage? = nil
    ) {
        self.threadId = threadId
        self.workflowId = workflowId
        self.workflowName = workflowName
        self.pythonCode = pythonCode
        self.executionLog = executionLog
        self.status = status
        self.startedAt = startedAt
        self.completedAt = completedAt
        self.durationMs = durationMs
        self.error = error
        self.workflowSnapshot = workflowSnapshot
        self.nodeNameMap = nodeNameMap
        self.progressTimeline = progressTimeline
        self.diagramMermaid = diagramMermaid
        self.runArtifacts = runArtifacts
        self.steps = steps
        self.runUsage = runUsage
    }
}

// MARK: - Run Usage & Cost (2026-09-03)

/// Tokens and money for one run, mirroring the server's `RunUsageResponse`.
///
/// The three states the server keeps apart are kept apart here too, because
/// collapsing them is exactly how a cost display starts lying:
/// - `priced` with a cost → that is the cost.
/// - `priced` with a cost of 0 → genuinely free; every call ran on-device.
/// - not `priced` → nobody could price these models, `costUsd` is nil, and
///   the UI says "Cost unpriced" rather than inventing a zero.
struct RunUsage: Codable, Equatable {
    let modelCalls: Int
    let inputTokens: Int
    let outputTokens: Int
    let totalTokens: Int
    let cacheReadTokens: Int
    /// Nil when nothing could be priced. Never a stand-in zero.
    let costUsd: Double?
    /// True only when EVERY call in the run priced.
    let priced: Bool
    /// Some calls priced and some did not — `costUsd` is a floor.
    let partiallyPriced: Bool
    /// At least one call's tokens are a character-count estimate rather than
    /// the provider's own count.
    let estimatedTokens: Bool
    let unpricedModels: [String]

    enum CodingKeys: String, CodingKey {
        case modelCalls = "model_calls"
        case inputTokens = "input_tokens"
        case outputTokens = "output_tokens"
        case totalTokens = "total_tokens"
        case cacheReadTokens = "cache_read_tokens"
        case costUsd = "cost_usd"
        case priced
        case partiallyPriced = "partially_priced"
        case estimatedTokens = "estimated_tokens"
        case unpricedModels = "unpriced_models"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        modelCalls = try container.decodeIfPresent(Int.self, forKey: .modelCalls) ?? 0
        inputTokens = try container.decodeIfPresent(Int.self, forKey: .inputTokens) ?? 0
        outputTokens = try container.decodeIfPresent(Int.self, forKey: .outputTokens) ?? 0
        totalTokens = try container.decodeIfPresent(Int.self, forKey: .totalTokens) ?? 0
        cacheReadTokens = try container.decodeIfPresent(Int.self, forKey: .cacheReadTokens) ?? 0
        costUsd = try container.decodeIfPresent(Double.self, forKey: .costUsd)
        priced = try container.decodeIfPresent(Bool.self, forKey: .priced) ?? false
        partiallyPriced = try container.decodeIfPresent(Bool.self, forKey: .partiallyPriced) ?? false
        estimatedTokens = try container.decodeIfPresent(Bool.self, forKey: .estimatedTokens) ?? false
        unpricedModels = try container.decodeIfPresent([String].self, forKey: .unpricedModels) ?? []
    }

    init(
        modelCalls: Int = 0,
        inputTokens: Int = 0,
        outputTokens: Int = 0,
        totalTokens: Int = 0,
        cacheReadTokens: Int = 0,
        costUsd: Double? = nil,
        priced: Bool = false,
        partiallyPriced: Bool = false,
        estimatedTokens: Bool = false,
        unpricedModels: [String] = []
    ) {
        self.modelCalls = modelCalls
        self.inputTokens = inputTokens
        self.outputTokens = outputTokens
        self.totalTokens = totalTokens
        self.cacheReadTokens = cacheReadTokens
        self.costUsd = costUsd
        self.priced = priced
        self.partiallyPriced = partiallyPriced
        self.estimatedTokens = estimatedTokens
        self.unpricedModels = unpricedModels
    }

    /// True when there is anything at all to report.
    var hasUsage: Bool { modelCalls > 0 }

    /// What to print for the money. Four outcomes, none of them a bare zero
    /// standing in for an unknown:
    /// - "Free" — priced at exactly nothing, i.e. it all ran on this machine.
    /// - "$0.0132" — the cost.
    /// - "≥ $0.0132" — a floor: some calls could not be priced.
    /// - "Cost unpriced" — no price exists for these models.
    var costText: String {
        guard let cost = costUsd else { return "Cost unpriced" }
        if partiallyPriced {
            return "≥ \(Self.currency(cost))"
        }
        return cost == 0 ? "Free" : Self.currency(cost)
    }

    /// "12,431 tokens · 3 calls", with the estimate flagged when the tokens
    /// were guessed rather than reported.
    var tokensText: String {
        let calls = modelCalls == 1 ? "1 call" : "\(modelCalls) calls"
        let prefix = estimatedTokens ? "~" : ""
        return "\(prefix)\(totalTokens.formatted()) tokens · \(calls)"
    }

    /// The models nobody could price, for the tooltip that explains why the
    /// cost is missing. Nil when everything priced.
    var unpricedNotice: String? {
        guard !unpricedModels.isEmpty else { return nil }
        return "No registry price for: " + unpricedModels.joined(separator: ", ")
    }

    /// Sub-cent costs need more than two decimals to say anything at all.
    private static func currency(_ value: Double) -> String {
        if value > 0 && value < 0.01 {
            return String(format: "$%.4f", value)
        }
        return String(format: "$%.2f", value)
    }
}

// MARK: - Run Artifact Provenance (#4313)

/// One artifact produced by a workflow run, with navigation targets.
/// Mirrors the server's `WorkflowRunArtifactResponse`.
struct WorkflowRunArtifact: Codable, Identifiable, Equatable {
    let artifactId: String
    let artifactType: String
    let documentId: String
    let documentName: String?
    let sourceDocumentId: String?
    let sourceDocumentName: String?
    let runId: String?
    let stepName: String?
    let nodeName: String?
    let sequence: Int?
    let createdAt: String?
    /// Which provider/model actually produced this artifact (#4284). The
    /// node-level provider/model is what the workflow was CONFIGURED with;
    /// this is what ran. They diverge on run-level overrides and fallbacks,
    /// so provenance has to be read per artifact, not per node.
    let provider: String?
    let model: String?
    /// Length of the STORED content, in characters — not the preview's
    /// length. This is what makes an honest "showing 2,000 of 12,431" line
    /// possible.
    let contentChars: Int?
    /// A preview only. `contentTruncated` says whether it is the whole
    /// content; the full artifact stays addressable at
    /// `GET /api/artifacts/{artifact_id}`. Truncation lives in the RESPONSE,
    /// never in what was stored — rendering this as if it were complete
    /// would silently misreport a transcription.
    let contentPreview: String?
    let contentTruncated: Bool?
    let hasStructuredData: Bool?

    var id: String { artifactId }

    /// True only when the server said the preview is clipped. A nil field is
    /// an old response that never carried the flag, not a promise that the
    /// preview is complete — but there is no preview to over-claim in that
    /// case either, so false is safe here.
    var isTruncated: Bool { contentTruncated == true }

    /// The sentence to show beside a clipped preview, or nil when what is
    /// held IS the whole content. Never softened into "long content": the
    /// reader has to be able to tell a short transcription from a clipped
    /// one, and only the character counts do that.
    var truncationNotice: String? {
        guard isTruncated else { return nil }
        let shown = (contentPreview ?? "").count
        guard let total = contentChars, total > shown else {
            // Truncated, but the server did not say by how much. Still say it
            // is incomplete — an unknown remainder is not no remainder.
            return "Preview only — this is not the full text"
        }
        return "Preview only — showing \(shown.formatted()) of \(total.formatted()) characters"
    }

    /// "anthropic · claude-sonnet-4-6", or nil when the server recorded
    /// neither. Never a placeholder: an artifact with no recorded origin must
    /// read as having no recorded origin.
    var providerModelText: String? {
        let parts = [provider, model].compactMap { value -> String? in
            guard let value, !value.isEmpty else { return nil }
            return value
        }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    enum CodingKeys: String, CodingKey {
        case artifactId = "artifact_id"
        case artifactType = "artifact_type"
        case documentId = "document_id"
        case documentName = "document_name"
        case sourceDocumentId = "source_document_id"
        case sourceDocumentName = "source_document_name"
        case runId = "run_id"
        case stepName = "step_name"
        case nodeName = "node_name"
        case sequence
        case createdAt = "created_at"
        case provider
        case model
        case contentChars = "content_chars"
        case contentPreview = "content_preview"
        case contentTruncated = "content_truncated"
        case hasStructuredData = "has_structured_data"
    }
}
