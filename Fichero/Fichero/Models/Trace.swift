import Foundation

// MARK: - Trace Model

/// Debug data from LangChain/LangGraph execution.
/// Matches Python Trace model in fichero/models.py
///
/// Captures detailed information about each AI call:
/// - What was called (model, provider)
/// - Inputs and outputs
/// - Timing and cost
/// - Errors
///
/// Used for debugging, cost tracking, and optimization.
struct Trace: Identifiable, Codable, Hashable {
    let id: String
    var runId: String

    // Hierarchy (LangGraph has nested calls)
    var parentTraceId: String?
    var sequence: Int

    // What executed
    var name: String
    var traceType: String

    // Status
    var status: String
    var error: String?

    // I/O
    var inputs: [String: AnyCodable]?
    var outputs: [String: AnyCodable]?

    // Timing
    var startedAt: Date
    var endedAt: Date?
    var latencyMs: Int?

    // Cost tracking
    var model: String?
    var tokensIn: Int
    var tokensOut: Int
    var costUsd: Double

    // Extra
    var metadata: [String: AnyCodable]

    enum CodingKeys: String, CodingKey {
        case id
        case runId = "run_id"
        case parentTraceId = "parent_trace_id"
        case sequence
        case name
        case traceType = "trace_type"
        case status
        case error
        case inputs
        case outputs
        case startedAt = "started_at"
        case endedAt = "ended_at"
        case latencyMs = "latency_ms"
        case model
        case tokensIn = "tokens_in"
        case tokensOut = "tokens_out"
        case costUsd = "cost_usd"
        case metadata
    }

    init(
        id: String = UUID().uuidString,
        runId: String,
        parentTraceId: String? = nil,
        sequence: Int = 0,
        name: String,
        traceType: String,
        status: String = "running",
        error: String? = nil,
        inputs: [String: AnyCodable]? = nil,
        outputs: [String: AnyCodable]? = nil,
        startedAt: Date = Date(),
        endedAt: Date? = nil,
        latencyMs: Int? = nil,
        model: String? = nil,
        tokensIn: Int = 0,
        tokensOut: Int = 0,
        costUsd: Double = 0.0,
        metadata: [String: AnyCodable] = [:]
    ) {
        self.id = id
        self.runId = runId
        self.parentTraceId = parentTraceId
        self.sequence = sequence
        self.name = name
        self.traceType = traceType
        self.status = status
        self.error = error
        self.inputs = inputs
        self.outputs = outputs
        self.startedAt = startedAt
        self.endedAt = endedAt
        self.latencyMs = latencyMs
        self.model = model
        self.tokensIn = tokensIn
        self.tokensOut = tokensOut
        self.costUsd = costUsd
        self.metadata = metadata
    }
}

// MARK: - Trace Type Helpers

extension Trace {
    /// Common trace types
    enum TraceType: String {
        case llm
        case chain
        case tool
        case retriever
        case agent
    }

    /// Check if this is an LLM call trace
    var isLLMCall: Bool {
        traceType == TraceType.llm.rawValue
    }

    /// Check if this is a tool call trace
    var isToolCall: Bool {
        traceType == TraceType.tool.rawValue
    }

    /// Display name for the trace type
    var traceTypeDisplayName: String {
        switch traceType {
        case "llm": return "LLM Call"
        case "chain": return "Chain"
        case "tool": return "Tool"
        case "retriever": return "Retriever"
        case "agent": return "Agent"
        default: return traceType.capitalized
        }
    }

    /// Icon for the trace type
    var traceTypeIcon: String {
        switch traceType {
        case "llm": return "brain"
        case "chain": return "link"
        case "tool": return "wrench"
        case "retriever": return "magnifyingglass"
        case "agent": return "person.circle"
        default: return "questionmark.circle"
        }
    }

    /// Total tokens used
    var totalTokens: Int {
        tokensIn + tokensOut
    }

    /// Duration calculated from timestamps
    var duration: TimeInterval? {
        guard let end = endedAt else { return nil }
        return end.timeIntervalSince(startedAt)
    }

    /// Formatted latency string
    var latencyString: String? {
        guard let latency = latencyMs else { return nil }
        if latency < 1000 {
            return "\(latency)ms"
        } else {
            return String(format: "%.2fs", Double(latency) / 1000.0)
        }
    }

    /// Cost formatted as currency
    var costFormatted: String {
        String(format: "$%.6f", costUsd)
    }

    /// Whether this trace has errors
    var hasError: Bool {
        status == "failed" || error != nil
    }
}
