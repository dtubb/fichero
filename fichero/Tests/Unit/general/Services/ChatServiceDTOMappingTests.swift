@testable import Fichero
import XCTest

/// Tests for the ChatService response DTOs and their mappers to local models.
/// DocumentSourceAPI/ChatMessageAPI/ConversationSummary/ConversationDetail were
/// untested — snake_case decode plus the toDocumentSource()/toChatMessage()
/// conversions. Pure value logic, no live engine.
final class ChatServiceDTOMappingTests: XCTestCase {

    // MARK: - DocumentSourceAPI

    func testDocumentSourceAPIDecodesSnakeCase() throws {
        let json = Data("""
        {
            "document_id": "doc-1",
            "document_name": "Report.pdf",
            "excerpt": "…relevant text…",
            "relevance_score": 0.92
        }
        """.utf8)
        let api = try JSONDecoder().decode(DocumentSourceAPI.self, from: json)
        XCTAssertEqual(api.documentId, "doc-1")     // ← document_id
        XCTAssertEqual(api.documentName, "Report.pdf")  // ← document_name
        XCTAssertEqual(api.relevanceScore, 0.92)    // ← relevance_score
        XCTAssertEqual(api.id, "doc-1")             // id == documentId
    }

    func testDocumentSourceAPIMapsToLocalModel() {
        let api = DocumentSourceAPI(documentId: "doc-9", documentName: "Notes",
                                    excerpt: "snippet", relevanceScore: 0.5)
        let source = api.toDocumentSource()
        XCTAssertEqual(source.id, "doc-9")
        XCTAssertEqual(source.documentId, "doc-9")
        XCTAssertEqual(source.documentName, "Notes")
        XCTAssertEqual(source.excerpt, "snippet")
        XCTAssertEqual(source.relevanceScore, 0.5)
    }

    // MARK: - ChatMessageAPI.toChatMessage

    func testChatMessageMapsUserRole() {
        let msg = ChatMessageAPI(role: "user", content: "hi").toChatMessage()
        XCTAssertEqual(msg.role, .user)
        XCTAssertEqual(msg.content, "hi")
    }

    /// Any non-"user" role collapses to .assistant — including "system", which
    /// has its own ChatRole case that this mapper deliberately does not use.
    func testChatMessageNonUserRolesCollapseToAssistant() {
        XCTAssertEqual(ChatMessageAPI(role: "assistant", content: "a").toChatMessage().role, .assistant)
        XCTAssertEqual(ChatMessageAPI(role: "system", content: "s").toChatMessage().role, .assistant)
        XCTAssertEqual(ChatMessageAPI(role: "tool", content: "t").toChatMessage().role, .assistant)
    }

    // MARK: - Conversation DTOs (snake_case decode)

    func testConversationSummaryDecodesSnakeCase() throws {
        let json = Data("""
        {
            "id": "c-1",
            "title": "My Chat",
            "message_count": 7,
            "created_at": "2026-05-10T10:00:00Z",
            "updated_at": "2026-05-11T10:00:00Z",
            "folder_path": "/chats",
            "sort_order": 3
        }
        """.utf8)
        let summary = try JSONDecoder().decode(ConversationSummary.self, from: json)
        XCTAssertEqual(summary.id, "c-1")
        XCTAssertEqual(summary.messageCount, 7)      // ← message_count
        XCTAssertEqual(summary.folderPath, "/chats") // ← folder_path
        XCTAssertEqual(summary.sortOrder, 3)         // ← sort_order
    }

    func testConversationDetailDecodesMessagesAndSnakeCase() throws {
        let json = Data("""
        {
            "id": "c-2",
            "title": "Threaded",
            "messages": [
                {"role": "user", "content": "q"},
                {"role": "assistant", "content": "a"}
            ],
            "created_at": "2026-05-10T10:00:00Z",
            "updated_at": "2026-05-11T10:00:00Z",
            "folder_path": "/",
            "sort_order": 0
        }
        """.utf8)
        let detail = try JSONDecoder().decode(ConversationDetail.self, from: json)
        XCTAssertEqual(detail.messages.count, 2)
        XCTAssertEqual(detail.messages.first?.role, "user")
        XCTAssertEqual(detail.messages.last?.content, "a")
        XCTAssertEqual(detail.folderPath, "/")
        // Mapping the decoded API messages yields local ChatMessages.
        let mapped = detail.messages.map { $0.toChatMessage() }
        XCTAssertEqual(mapped.map(\.role), [.user, .assistant])
    }
}
