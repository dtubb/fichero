import Foundation
import Combine

/// Service for RAG chat operations via the Fichero backend.
@MainActor
class ChatService: ObservableObject {
    private let api: APIClient

    init(apiClient: APIClient) {
        self.api = apiClient
    }

    // MARK: - Chat

    /// Send a chat message and get a RAG response.
    func chat(
        message: String,
        conversationId: String? = nil,
        documentIds: [String]? = nil,
        includeSources: Bool = true,
        maxSources: Int = 5,
        provider: String? = nil,
        model: String? = nil
    ) async throws -> ChatAPIResponse {
        let request = ChatAPIRequest(
            message: message,
            conversationId: conversationId,
            documentIds: documentIds,
            includeSources: includeSources,
            maxSources: maxSources,
            provider: provider,
            model: model
        )
        return try await api.post("/chat", body: request)
    }

    // MARK: - Providers

    /// List available LLM providers.
    func listProviders() async throws -> [LLMProvider] {
        try await api.get("/chat/providers")
    }

    // MARK: - Text Extraction

    /// Extract text from documents (populates page_content for search/chat).
    func extractText(documentIds: [String]? = nil, force: Bool = false) async throws -> ExtractTextResponse {
        let request = ExtractTextRequest(documentIds: documentIds, force: force)
        return try await api.post("/chat/extract-text", body: request)
    }

    // MARK: - Conversations

    /// List all conversations.
    func listConversations() async throws -> [ConversationSummary] {
        try await api.get("/chat/conversations")
    }

    /// Get a conversation with full message history.
    func getConversation(_ id: String) async throws -> ConversationDetail {
        try await api.get("/chat/conversations/\(id)")
    }

    /// Delete a conversation.
    func deleteConversation(_ id: String) async throws {
        try await api.delete("/chat/conversations/\(id)")
    }
}

// MARK: - Request Models

struct ChatAPIRequest: Codable {
    let message: String
    let conversationId: String?
    let documentIds: [String]?
    let includeSources: Bool
    let maxSources: Int
    let provider: String?
    let model: String?

    enum CodingKeys: String, CodingKey {
        case message
        case conversationId = "conversation_id"
        case documentIds = "document_ids"
        case includeSources = "include_sources"
        case maxSources = "max_sources"
        case provider
        case model
    }
}

struct ExtractTextRequest: Codable {
    let documentIds: [String]?
    let force: Bool

    enum CodingKeys: String, CodingKey {
        case documentIds = "document_ids"
        case force
    }
}

// MARK: - Response Models

struct ChatAPIResponse: Codable {
    let message: String
    let sources: [DocumentSourceAPI]
    let conversationId: String
    let modelUsed: String?

    enum CodingKeys: String, CodingKey {
        case message
        case sources
        case conversationId = "conversation_id"
        case modelUsed = "model_used"
    }
}

struct LLMProvider: Codable, Identifiable {
    let id: String
    let name: String
    let models: [String]
    let available: Bool
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

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case messageCount = "message_count"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct ConversationDetail: Codable, Identifiable {
    let id: String
    let title: String
    let messages: [ChatMessageAPI]
    let createdAt: String
    let updatedAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case messages
        case createdAt = "created_at"
        case updatedAt = "updated_at"
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
