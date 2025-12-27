import Foundation
import Combine

/// Service for managing chat conversations via the backend API.
@MainActor
class ConversationService: ObservableObject {
    private let api = APIClient.shared

    // MARK: - Published State

    /// All conversations loaded from backend
    @Published var conversations: [Conversation] = []

    // MARK: - List Conversations

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

    /// Duplicate a conversation.
    func duplicateConversation(_ id: String) async throws -> ConversationAPI {
        return try await api.post("/chat/conversations/\(id)/duplicate")
    }

    /// Load conversations from backend and update @Published property
    func loadConversations() async throws {
        let summaries = try await listConversations()
        conversations = summaries.map { summary in
            Conversation(
                id: summary.id,
                title: summary.title,
                messages: [],  // Messages loaded on demand
                documentScope: []
            )
        }
    }

    /// Convert API summaries to local Conversation models for sidebar.
    func getConversationsForSidebar() async throws -> [Conversation] {
        let summaries = try await listConversations()
        return summaries.map { summary in
            Conversation(
                id: summary.id,
                title: summary.title,
                messages: [],  // Messages loaded on demand
                documentScope: []
            )
        }
    }

    /// Rename a conversation.
    func renameConversation(_ id: String, newTitle: String) async throws -> ConversationAPI {
        let update = ConversationUpdate(title: newTitle)
        return try await api.patch("/chat/conversations/\(id)", body: update)
    }

    /// Reorder conversations.
    func reorderConversations(_ conversationIds: [String], folderPath: String = "/") async throws {
        let request: ConversationReorderRequest = ConversationReorderRequest(
            conversationIds: conversationIds,
            folderPath: folderPath
        )
        try await api.postVoid("/chat/conversations/reorder", body: request)
    }
}

// MARK: - Request Models

struct ConversationUpdate: Encodable {
    let title: String
}

struct ConversationReorderRequest: Encodable {
    let conversationIds: [String]
    let folderPath: String

    enum CodingKeys: String, CodingKey {
        case conversationIds = "conversation_ids"
        case folderPath = "folder_path"
    }
}

// MARK: - Response Models

struct ConversationAPI: Codable, Identifiable {
    let id: String
    let title: String
    let messageCount: Int
    let createdAt: String
    let updatedAt: String
    let folderPath: String
    let sortOrder: Int

    enum CodingKeys: String, CodingKey {
        case id, title
        case messageCount = "message_count"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case folderPath = "folder_path"
        case sortOrder = "sort_order"
    }
}
