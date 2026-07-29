import Observation
import Foundation
import Combine
import OSLog
import FicheroAPIClient
import OpenAPIRuntime

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ConversationService")

/// ConversationService using the generated OpenAPI client.
/// This replaces the manual APIClient with type-safe generated calls.
@MainActor
@Observable
class ConversationService {
    private let client: FicheroClient

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    // MARK: - Published State

    /// All conversations loaded from backend
    var conversations: [Conversation] = []

    // MARK: - API Methods

    /// List all conversations.  GET /api/chat/conversations
    func listConversations() async throws -> [ConversationSummary] {
        let response = try await client.api.listConversationsApiChatConversationsGet(.init())

        switch response {
        case .ok(let okResponse):
            let jsonArray = try okResponse.body.json
            // Parse untyped response into ConversationSummary
            return try jsonArray.items.map { item in
                try parseConversationSummary(from: item.additionalProperties)
            }
        default:
            throw ConversationServiceError.unexpectedResponse
        }
    }

    /// Create an EMPTY conversation — no LLM turn required (#4308).
    /// POST /api/chat/conversations (the audited `conversation.create` action).
    ///
    /// "New Chat" used to be a full `POST /api/chat` LLM round-trip; with no
    /// provider configured it silently created nothing and the sidebar stayed
    /// empty. This persists first; the first real message continues the id.
    func createConversation(
        title: String? = nil,
        folderPath: String = "/"
    ) async throws -> Conversation {
        let request = Components.Schemas.ConversationCreateRequest(
            title: title,
            folderPath: folderPath
        )
        let response = try await client.api.createConversationApiChatConversationsPost(.init(
            body: .json(request)
        ))

        switch response {
        case .ok(let okResponse):
            let history = try okResponse.body.json
            let conversation = Conversation(
                id: history.id,
                title: history.title,
                messages: [],
                documentScope: [],
                folderPath: history.folderPath ?? "/",
                sortOrder: history.sortOrder ?? 0
            )
            // Append the one new item in place — observers rebuild the sidebar.
            conversations.append(conversation)
            return conversation
        default:
            throw ConversationServiceError.unexpectedResponse
        }
    }

    /// Get a conversation with full message history.  GET /api/chat/conversations/{conversation_id}
    func getConversation(_ id: String) async throws -> ConversationDetail {
        let response = try await client.api.getConversationApiChatConversationsConversationIdGet(.init(
            path: .init(conversationId: id),
        ))

        switch response {
        case .ok(let okResponse):
            let history = try okResponse.body.json
            return convertToConversationDetail(history)
        default:
            throw ConversationServiceError.unexpectedResponse
        }
    }

    /// Delete a conversation.  DELETE /api/chat/conversations/{conversation_id}
    func deleteConversation(_ id: String) async throws {
        let response = try await client.api.deleteConversationApiChatConversationsConversationIdDelete(.init(
            path: .init(conversationId: id),
        ))

        switch response {
        case .ok:
            // Update local array to trigger UI refresh
            conversations.removeAll { $0.id == id }
            return
        default:
            throw ConversationServiceError.unexpectedResponse
        }
    }

    /// Duplicate a conversation.  POST /api/chat/conversations/{conversation_id}/duplicate
    func duplicateConversation(_ id: String) async throws -> ConversationAPI {
        let response = try await client.api.duplicateConversationApiChatConversationsConversationIdDuplicatePost(.init(
            path: .init(conversationId: id),
        ))

        switch response {
        case .ok(let okResponse):
            let payload = try okResponse.body.json
            return ConversationAPI(
                id: payload.id,
                title: payload.title,
                messageCount: payload.messageCount,
                createdAt: payload.createdAt,
                updatedAt: payload.updatedAt,
                folderPath: payload.folderPath,
                sortOrder: payload.sortOrder
            )
        default:
            throw ConversationServiceError.unexpectedResponse
        }
    }

    /// Rename a conversation.
    func renameConversation(_ id: String, newTitle: String) async throws -> ConversationAPI {
        return try await updateConversation(id, title: newTitle)
    }

    /// Update a conversation.  PUT /api/chat/conversations/{conversation_id}
    func updateConversation(
        _ id: String,
        title: String? = nil,
        folderPath: String? = nil
    ) async throws -> ConversationAPI {
        // Use typed fields so writes reach the declared Pydantic attributes.
        // Bypassing them via additionalProperties produced silent save losses
        // under extra="allow" on the server. See 31fc4141 for details.
        let request = Components.Schemas.ConversationUpdate(
            title: title,
            folderPath: folderPath
        )

        let response = try await client.api.updateConversationApiChatConversationsConversationIdPut(.init(
            path: .init(conversationId: id),
            body: .json(request)
        ))

        switch response {
        case .ok(let okResponse):
            let history = try okResponse.body.json
            let result = convertHistoryToAPI(history)

            // Update local array to trigger UI refresh
            if let index = conversations.firstIndex(where: { $0.id == id }) {
                if let newTitle = title {
                    conversations[index].title = newTitle
                }
                if let newFolderPath = folderPath {
                    conversations[index].folderPath = newFolderPath
                }
            }

            return result
        default:
            throw ConversationServiceError.unexpectedResponse
        }
    }

    /// Move conversation to a different folder.
    func moveToFolder(_ id: String, folderPath: String) async throws -> ConversationAPI {
        return try await updateConversation(id, folderPath: folderPath)
    }

    /// Reorder conversations.  POST /api/chat/conversations/reorder
    func reorderConversations(_ conversationIds: [String], folderPath: String = "/") async throws {
        let response = try await client.api.reorderConversationsApiChatConversationsReorderPost(.init(
            query: .init(folderPath: folderPath),
            body: .json(conversationIds)
        ))

        switch response {
        case .ok:
            return
        default:
            throw ConversationServiceError.unexpectedResponse
        }
    }

    /// Load conversations from backend and update property
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

    // MARK: - Type Conversion

    /// Parse untyped OpenAPI container to ConversationSummary
    private func parseConversationSummary(from container: OpenAPIObjectContainer) throws -> ConversationSummary {
        let dict = container.value as [String: any Sendable]
        guard let id = dict["id"] as? String,
              let title = dict["title"] as? String else {
            throw ConversationServiceError.invalidData
        }

        return ConversationSummary(
            id: id,
            title: title,
            messageCount: dict["message_count"] as? Int ?? 0,
            createdAt: dict["created_at"] as? String ?? "",
            updatedAt: dict["updated_at"] as? String ?? "",
            folderPath: dict["folder_path"] as? String ?? "/",
            sortOrder: dict["sort_order"] as? Int ?? 0
        )
    }

    /// Convert generated ConversationHistory to ConversationDetail
    private func convertToConversationDetail(_ history: Components.Schemas.ConversationHistory) -> ConversationDetail {
        ConversationDetail(
            id: history.id,
            title: history.title,
            messages: history.messages.map { msg in
                ChatMessageAPI(
                    role: msg.role,
                    content: msg.content
                )
            },
            createdAt: history.createdAt,
            updatedAt: history.updatedAt,
            folderPath: history.folderPath ?? "/",
            sortOrder: history.sortOrder ?? 0
        )
    }

    /// Convert ConversationHistory to ConversationAPI
    private func convertHistoryToAPI(_ history: Components.Schemas.ConversationHistory) -> ConversationAPI {
        ConversationAPI(
            id: history.id,
            title: history.title,
            messageCount: history.messages.count,
            createdAt: history.createdAt,
            updatedAt: history.updatedAt,
            folderPath: history.folderPath ?? "/",
            sortOrder: history.sortOrder ?? 0
        )
    }

    /// Parse untyped OpenAPI container to ConversationAPI
    private func parseConversationAPI(from container: OpenAPIObjectContainer) throws -> ConversationAPI {
        let dict = container.value as [String: any Sendable]
        guard let id = dict["id"] as? String,
              let title = dict["title"] as? String else {
            throw ConversationServiceError.invalidData
        }

        let messages = dict["messages"] as? [[String: any Sendable]] ?? []

        return ConversationAPI(
            id: id,
            title: title,
            messageCount: messages.count,
            createdAt: dict["created_at"] as? String ?? "",
            updatedAt: dict["updated_at"] as? String ?? "",
            folderPath: dict["folder_path"] as? String ?? "/",
            sortOrder: dict["sort_order"] as? Int ?? 0
        )
    }
}

// MARK: - Error Types

enum ConversationServiceError: Error, LocalizedError {
    case unexpectedResponse
    case invalidData
    case notFound

    var errorDescription: String? {
        switch self {
        case .unexpectedResponse:
            return "Unexpected response from server"
        case .invalidData:
            return "Invalid data received"
        case .notFound:
            return "Conversation not found"
        }
    }
}

// MARK: - API Response Types

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
