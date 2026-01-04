import Foundation
import Combine

/// Service for managing chat conversations via the backend API.
@MainActor
class ConversationService: ObservableObject {
    private let api: APIClient

    init(apiClient: APIClient) {
        self.api = apiClient
    }

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
                documentScope: [],
                folderPath: summary.folderPath,
                sortOrder: summary.sortOrder
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
                documentScope: [],
                folderPath: summary.folderPath,
                sortOrder: summary.sortOrder
            )
        }
    }

    /// Rename a conversation.
    func renameConversation(_ id: String, newTitle: String) async throws -> ConversationAPI {
        let update = ConversationUpdate(title: newTitle)
        return try await api.put("/chat/conversations/\(id)", body: update)
    }

    /// Update a conversation.
    func updateConversation(
        _ id: String,
        title: String? = nil,
        folderPath: String? = nil
    ) async throws -> ConversationAPI {
        let update = ConversationUpdate(
            title: title,
            folderPath: folderPath
        )
        return try await api.put("/chat/conversations/\(id)", body: update)
    }

    /// Move conversation to a different folder.
    func moveToFolder(_ id: String, folderPath: String) async throws -> ConversationAPI {
        return try await updateConversation(id, folderPath: folderPath)
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
    let title: String?
    let folderPath: String?

    enum CodingKeys: String, CodingKey {
        case title
        case folderPath = "folder_path"
    }

    init(title: String? = nil, folderPath: String? = nil) {
        self.title = title
        self.folderPath = folderPath
    }
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
