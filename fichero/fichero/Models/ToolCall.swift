import Foundation

// MARK: - ToolCall — the shared agentic spine

/// One tool call the agent made during a chat turn. This is the **product**
/// spine every kind of agent action collapses onto — a research Step, a chat
/// tool call, an MCP mutation, and a compare node are all `ToolCall`s (see
/// `docs/design/agentic-surface-consolidation-fabel-review.md`, §3).
///
/// Not to be confused with `Trace` (`Models/Trace.swift`), which is a *debug*
/// record (timing/cost/IO of an LLM/chain call). `ToolCall` is what the user
/// sees: *the model did an audited thing.* Honours "AI = instrument, not
/// interlocutor" — it surfaces the fact + provenance, it does not narrate.
///
/// Decodes as an optional array on `ChatMessage` (`tool_calls`), so it is nil
/// against today's single-shot RAG `/api/chat` and lights up the day the engine
/// wires `chat_tools.py` and emits `tool_calls[]` (migration step 2, engine).
struct ToolCall: Identifiable, Codable, Hashable {
    let id: String

    /// The workspace (node) this call ran inside, when there is one.
    var workspaceId: String?
    /// The chat message that produced this call, when it came from a chat turn.
    var messageId: String?
    /// The plan task that produced this call, when it came from the plan.
    var taskId: String?

    /// Canonical registry action invoked (e.g. `document.move`).
    var actionName: String
    var params: [String: AnyCodable]?

    /// The user account that acted — a human or a model-user (#1847). Every call
    /// has an actor; that is the point of "the model is a user."
    var actor: String

    /// The `ActionAudit` row id. **Required for mutating calls** — a mutation
    /// without an `auditId` is unaudited and violates #1848; the card flags it.
    var auditId: String?

    var status: Status

    enum Status: String, Codable, Hashable {
        case pending
        case running
        case ok
        case error
    }

    enum CodingKeys: String, CodingKey {
        case id
        case workspaceId = "workspace_id"
        case messageId = "message_id"
        case taskId = "task_id"
        case actionName = "action_name"
        case params
        case actor
        case auditId = "audit_id"
        case status
    }

    init(
        id: String = UUID().uuidString,
        workspaceId: String? = nil,
        messageId: String? = nil,
        taskId: String? = nil,
        actionName: String,
        params: [String: AnyCodable]? = nil,
        actor: String,
        auditId: String? = nil,
        status: Status = .ok
    ) {
        self.id = id
        self.workspaceId = workspaceId
        self.messageId = messageId
        self.taskId = taskId
        self.actionName = actionName
        self.params = params
        self.actor = actor
        self.auditId = auditId
        self.status = status
    }
}

// MARK: - Display helpers

extension ToolCall {
    /// True when this call carries an audit trail. A mutating call without one is
    /// the invariant we surface (see `isUnauditedMutation`).
    var isAudited: Bool { auditId?.isEmpty == false }

    /// SF Symbol for the current status.
    var statusIcon: String {
        switch status {
        case .pending: return "clock"
        case .running: return "arrow.triangle.2.circlepath"
        case .ok: return "checkmark.circle.fill"
        case .error: return "exclamationmark.triangle.fill"
        }
    }

    /// A stable, human-scannable one-liner of the params (sorted keys), e.g.
    /// `node_id: 42 · target: /Inbox`. Empty string when there are no params.
    var paramsSummary: String {
        guard let params, !params.isEmpty else { return "" }
        return params.keys.sorted()
            .map { key in "\(key): \(String(describing: params[key]!.value))" }
            .joined(separator: " · ")
    }
}
