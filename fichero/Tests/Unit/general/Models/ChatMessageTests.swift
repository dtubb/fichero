@testable import Fichero
import Foundation
import Testing

@Suite("ChatMessage")
struct ChatMessageTests {

    @Test("assistant messages retain sources and retrieval metadata through coding")
    func codingRoundTrip() throws {
        let timestamp = Date(timeIntervalSinceReferenceDate: 456)
        let message = ChatMessage(
            id: "message-1",
            role: .assistant,
            content: "Answer",
            sources: [
                DocumentSource(
                    id: "source-1",
                    documentId: "document-1",
                    documentName: "Letter.pdf",
                    excerpt: "Excerpt",
                    relevanceScore: 0.8
                )
            ],
            retrieval: RetrievalInfo(documentCount: 1, contextCount: 2, kgClaimsUsed: 3, kgEntitiesUsed: 4),
            timestamp: timestamp
        )

        let decoded = try JSONDecoder().decode(ChatMessage.self, from: JSONEncoder().encode(message))

        #expect(decoded.id == "message-1")
        #expect(decoded.role == .assistant)
        #expect(decoded.sources?.map(\.documentId) == ["document-1"])
        #expect(decoded.retrieval?.kgEntitiesUsed == 4)
        #expect(decoded.timestamp == timestamp)
    }

    @Test("all declared chat roles preserve their wire values")
    func chatRoleRawValues() throws {
        for role in [ChatRole.user, .assistant, .system] {
            let decoded = try JSONDecoder().decode(ChatRole.self, from: JSONEncoder().encode(role))
            #expect(decoded == role)
        }
    }
}
