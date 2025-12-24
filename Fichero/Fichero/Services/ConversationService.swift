import Foundation

/// Service for managing chat conversations via the backend API.
actor ConversationService {
    private let api = APIClient.shared

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
}
