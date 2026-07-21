import Foundation

// MARK: - Conversation (for RAG Chat)

struct Conversation: Identifiable, Codable, Hashable {
    let id: String
    var title: String
    var messages: [ChatMessage]
    var documentScope: [String]  // Document IDs to search within
    var folderPath: String
    var sortOrder: Int
    var createdAt: Date
    var updatedAt: Date

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case messages
        case documentScope = "document_ids"
        case folderPath = "folder_path"
        case sortOrder = "sort_order"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    init(
        id: String = UUID().uuidString,
        title: String = "New Chat",
        messages: [ChatMessage] = [],
        documentScope: [String] = [],
        folderPath: String = "/",
        sortOrder: Int = 0,
        createdAt: Date = Date(),
        updatedAt: Date = Date()
    ) {
        self.id = id
        self.title = title
        self.messages = messages
        self.documentScope = documentScope
        self.folderPath = folderPath
        self.sortOrder = sortOrder
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }
}

struct ChatMessage: Identifiable, Codable, Hashable {
    let id: String
    var role: ChatRole
    var content: String
    var sources: [DocumentSource]?
    // Retrieval done for THIS message (search-as-a-tool). Optional + ephemeral:
    // the backend stores only role/content, so — like `sources` — it is present
    // for a just-sent message and nil after a conversation reload.
    var retrieval: RetrievalInfo?
    // Audited tool calls the agent made producing THIS message (the ToolCall
    // spine). Optional + snake_case `tool_calls`: nil against today's single-shot
    // RAG /api/chat, decodes when the engine wires chat_tools.py (migration
    // step 2). See docs/design/agentic-surface-consolidation-fabel-review.md.
    var toolCalls: [ToolCall]?
    var timestamp: Date

    init(
        id: String = UUID().uuidString,
        role: ChatRole,
        content: String,
        sources: [DocumentSource]? = nil,
        retrieval: RetrievalInfo? = nil,
        toolCalls: [ToolCall]? = nil,
        timestamp: Date = Date()
    ) {
        self.id = id
        self.role = role
        self.content = content
        self.sources = sources
        self.retrieval = retrieval
        self.toolCalls = toolCalls
        self.timestamp = timestamp
    }

    enum CodingKeys: String, CodingKey {
        case id, role, content, sources, retrieval, timestamp
        case toolCalls = "tool_calls"
    }
}

/// What the chat's library search retrieved for one assistant message.
/// Makes the always-on RAG retrieval visible in the UI.
struct RetrievalInfo: Codable, Hashable {
    var documentCount: Int
    var contextCount: Int
    var kgClaimsUsed: Int
    var kgEntitiesUsed: Int

    /// True when the assistant actually pulled context from the library.
    var didSearch: Bool {
        contextCount > 0 || documentCount > 0 || kgClaimsUsed > 0 || kgEntitiesUsed > 0
    }

    /// Human summary, e.g. "Searched library · 5 documents · 3 claims".
    var summary: String {
        var parts = ["Searched library"]
        if documentCount > 0 {
            parts.append("\(documentCount) document\(documentCount == 1 ? "" : "s")")
        }
        if kgClaimsUsed > 0 {
            parts.append("\(kgClaimsUsed) claim\(kgClaimsUsed == 1 ? "" : "s")")
        }
        if kgEntitiesUsed > 0 {
            parts.append("\(kgEntitiesUsed) entit\(kgEntitiesUsed == 1 ? "y" : "ies")")
        }
        return parts.joined(separator: " · ")
    }
}

enum ChatRole: String, Codable, Hashable {
    case user
    case assistant
    case system
}

struct DocumentSource: Identifiable, Codable, Hashable {
    let id: String
    let documentId: String
    let documentName: String
    let excerpt: String
    let relevanceScore: Double
}
