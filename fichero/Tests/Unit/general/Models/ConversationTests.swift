@testable import Fichero
import Foundation
import Testing

@Suite("Conversation")
struct ConversationTests {

    @Test("defaults create an empty root-scoped chat")
    func defaults() {
        let conversation = Conversation()

        #expect(conversation.title == "New Chat")
        #expect(conversation.messages.isEmpty)
        #expect(conversation.documentScope.isEmpty)
        #expect(conversation.folderPath == "/")
        #expect(conversation.sortOrder == 0)
    }

    @Test("encodes and decodes document scope with backend snake-case keys")
    func codingKeysAndRoundTrip() throws {
        let timestamp = Date(timeIntervalSinceReferenceDate: 123)
        let conversation = Conversation(
            id: "chat-1",
            title: "Research",
            documentScope: ["doc-1", "doc-2"],
            folderPath: "/projects",
            sortOrder: 4,
            createdAt: timestamp,
            updatedAt: timestamp
        )

        let data = try JSONEncoder().encode(conversation)
        let json = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(json["document_ids"] as? [String] == ["doc-1", "doc-2"])
        #expect(json["folder_path"] as? String == "/projects")
        #expect(json["sort_order"] as? Int == 4)

        let decoded = try JSONDecoder().decode(Conversation.self, from: data)
        #expect(decoded.id == "chat-1")
        #expect(decoded.documentScope == ["doc-1", "doc-2"])
        #expect(decoded.createdAt == timestamp)
        #expect(decoded.updatedAt == timestamp)
    }
}
