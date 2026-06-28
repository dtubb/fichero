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

    enum CodingKeys: String, CodingKey {
        case message
        case sources
        case conversationId = "conversation_id"
        case modelUsed = "model_used"
        case documentCount = "document_count"
        case contextCount = "context_count"
        case kgClaimsUsed = "kg_claims_used"
        case kgEntitiesUsed = "kg_entities_used"
    }
}

struct LLMProvider: Codable, Identifiable {
    let id: String
    let name: String
    let models: [String]
    let available: Bool
    let supportsVision: Bool

    enum CodingKeys: String, CodingKey {
        case id, name, models, available
        case supportsVision = "supports_vision"
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
