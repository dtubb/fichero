import Foundation

// MARK: - Chat Response Models
// These types are shared across the app for chat-related functionality

struct ChatAPIResponse: Codable {
    let message: String
    let sources: [DocumentSourceAPI]
    let conversationId: String
    let modelUsed: String?
    // Retrieval telemetry — the search-as-a-tool step the chat backend always
    // runs (GraphAwareRetriever). Surfaced so the UI can show what was searched.
    let documentCount: Int
    let contextCount: Int
    let kgClaimsUsed: Int
    let kgEntitiesUsed: Int
    /// Audited tool calls the agent loop made during this turn (#1847/#2067).
    /// Empty on the single-shot RAG path; feeds `ChatMessage.toolCalls` so
    /// `ToolCallCard` shows which tools ran with what inputs.
    var toolCalls: [ToolCall] = []

    enum CodingKeys: String, CodingKey {
        case message
        case sources
        case conversationId = "conversation_id"
        case modelUsed = "model_used"
        case documentCount = "document_count"
        case contextCount = "context_count"
        case kgClaimsUsed = "kg_claims_used"
        case kgEntitiesUsed = "kg_entities_used"
        case toolCalls = "tool_calls"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        message = try container.decode(String.self, forKey: .message)
        sources = try container.decode([DocumentSourceAPI].self, forKey: .sources)
        conversationId = try container.decode(String.self, forKey: .conversationId)
        modelUsed = try container.decodeIfPresent(String.self, forKey: .modelUsed)
        documentCount = try container.decodeIfPresent(Int.self, forKey: .documentCount) ?? 0
        contextCount = try container.decodeIfPresent(Int.self, forKey: .contextCount) ?? 0
        kgClaimsUsed = try container.decodeIfPresent(Int.self, forKey: .kgClaimsUsed) ?? 0
        kgEntitiesUsed = try container.decodeIfPresent(Int.self, forKey: .kgEntitiesUsed) ?? 0
        toolCalls = try container.decodeIfPresent([ToolCall].self, forKey: .toolCalls) ?? []
    }

    init(
        message: String,
        sources: [DocumentSourceAPI],
        conversationId: String,
        modelUsed: String?,
        documentCount: Int,
        contextCount: Int,
        kgClaimsUsed: Int,
        kgEntitiesUsed: Int,
        toolCalls: [ToolCall] = []
    ) {
        self.message = message
        self.sources = sources
        self.conversationId = conversationId
        self.modelUsed = modelUsed
        self.documentCount = documentCount
        self.contextCount = contextCount
        self.kgClaimsUsed = kgClaimsUsed
        self.kgEntitiesUsed = kgEntitiesUsed
        self.toolCalls = toolCalls
    }
}

/// Per-model capability from the providers payload (#4187).
///
/// `supportsVision` is resolved SERVER-side: the engine's capability check is
/// tri-state (a model with no saved capabilities inherits the provider's
/// vision support — "unknown" is not "text-only"). Never re-derive this from
/// a capabilities list client-side; that hides every model whose row was
/// never populated, which is most of them on an existing install.
struct LLMProviderModelDetail: Codable, Hashable {
    let modelId: String
    let supportsVision: Bool

    enum CodingKeys: String, CodingKey {
        case modelId = "model_id"
        case supportsVision = "supports_vision"
    }
}

struct LLMProvider: Codable, Identifiable {
    let id: String
    let name: String
    let models: [String]
    let available: Bool
    let supportsVision: Bool
    /// May be empty on payloads predating #4187 — every lookup falls back to
    /// the provider-level `supportsVision`.
    var modelDetails: [LLMProviderModelDetail] = []

    enum CodingKeys: String, CodingKey {
        case id, name, models, available
        case supportsVision = "supports_vision"
        case modelDetails = "model_details"
    }

    init(
        id: String,
        name: String,
        models: [String],
        available: Bool,
        supportsVision: Bool,
        modelDetails: [LLMProviderModelDetail] = []
    ) {
        self.id = id
        self.name = name
        self.models = models
        self.available = available
        self.supportsVision = supportsVision
        self.modelDetails = modelDetails
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        name = try container.decode(String.self, forKey: .name)
        models = try container.decode([String].self, forKey: .models)
        available = try container.decode(Bool.self, forKey: .available)
        supportsVision = try container.decodeIfPresent(Bool.self, forKey: .supportsVision) ?? false
        modelDetails = try container.decodeIfPresent(
            [LLMProviderModelDetail].self, forKey: .modelDetails
        ) ?? []
    }
}

extension LLMProvider {
    /// Server-resolved vision capability for one model; a model absent from
    /// `modelDetails` inherits the provider's capability (tri-state, #4187).
    func supportsVision(model: String) -> Bool {
        modelDetails.first { $0.modelId == model }?.supportsVision ?? supportsVision
    }

    /// How this provider appears in a Run Workflow submenu (#4187).
    /// `nil` = hide the provider entirely.
    enum RunMenuEntry: Equatable {
        case providerOnly
        case models([String])
    }

    /// A provider with no configured models stays a bare button only when the
    /// provider itself is vision-capable; a provider whose model list filters
    /// to empty is hidden rather than demoted to a bare button (that would
    /// run its default, possibly text-only, model).
    func runMenuEntry(requiresVision: Bool) -> RunMenuEntry? {
        if models.isEmpty {
            return (!requiresVision || supportsVision) ? .providerOnly : nil
        }
        let shown = requiresVision ? models.filter { supportsVision(model: $0) } : models
        return shown.isEmpty ? nil : .models(shown)
    }
}

struct ExtractTextResponse: Codable {
    let extracted: Int
    let skipped: Int
    let failed: Int
    let errors: [String]
}

/// Document source from API response.
struct DocumentSourceAPI: Codable, Identifiable {
    let documentId: String
    let documentName: String
    let excerpt: String
    let relevanceScore: Double

    var id: String { documentId }

    enum CodingKeys: String, CodingKey {
        case documentId = "document_id"
        case documentName = "document_name"
        case excerpt
        case relevanceScore = "relevance_score"
    }

    /// Convert to local DocumentSource model.
    func toDocumentSource() -> DocumentSource {
        DocumentSource(
            id: documentId,
            documentId: documentId,
            documentName: documentName,
            excerpt: excerpt,
            relevanceScore: relevanceScore
        )
    }
}

struct ConversationSummary: Codable, Identifiable {
    let id: String
    let title: String
    let messageCount: Int
    let createdAt: String
    let updatedAt: String
    let folderPath: String
    let sortOrder: Int

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case messageCount = "message_count"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case folderPath = "folder_path"
        case sortOrder = "sort_order"
    }
}

struct ConversationDetail: Codable, Identifiable {
    let id: String
    let title: String
    let messages: [ChatMessageAPI]
    let createdAt: String
    let updatedAt: String
    let folderPath: String
    let sortOrder: Int

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case messages
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case folderPath = "folder_path"
        case sortOrder = "sort_order"
    }
}

struct ChatMessageAPI: Codable {
    let role: String
    let content: String

    /// Convert to local ChatMessage model.
    func toChatMessage() -> ChatMessage {
        let chatRole: ChatRole = role == "user" ? .user : .assistant
        return ChatMessage(role: chatRole, content: content)
    }
}
