@testable import Fichero
import XCTest

/// Tests for the chat retrieval summary — the "search-as-a-tool" line shown
/// under an assistant message (#2571 Stage 2). Pure formatting + gating logic.
final class RetrievalInfoTests: XCTestCase {

    func testDidSearchFalseWhenAllZero() {
        let info = RetrievalInfo(documentCount: 0, contextCount: 0, kgClaimsUsed: 0, kgEntitiesUsed: 0)
        XCTAssertFalse(info.didSearch)
    }

    func testDidSearchTrueWhenAnyContext() {
        XCTAssertTrue(RetrievalInfo(documentCount: 0, contextCount: 3, kgClaimsUsed: 0, kgEntitiesUsed: 0).didSearch)
        XCTAssertTrue(RetrievalInfo(documentCount: 1, contextCount: 0, kgClaimsUsed: 0, kgEntitiesUsed: 0).didSearch)
        XCTAssertTrue(RetrievalInfo(documentCount: 0, contextCount: 0, kgClaimsUsed: 2, kgEntitiesUsed: 0).didSearch)
        XCTAssertTrue(RetrievalInfo(documentCount: 0, contextCount: 0, kgClaimsUsed: 0, kgEntitiesUsed: 1).didSearch)
    }

    func testSummaryPluralization() {
        let one = RetrievalInfo(documentCount: 1, contextCount: 1, kgClaimsUsed: 1, kgEntitiesUsed: 1)
        XCTAssertEqual(one.summary, "Searched library · 1 document · 1 claim · 1 entity")

        let many = RetrievalInfo(documentCount: 5, contextCount: 5, kgClaimsUsed: 3, kgEntitiesUsed: 2)
        XCTAssertEqual(many.summary, "Searched library · 5 documents · 3 claims · 2 entities")
    }

    func testSummaryOmitsZeroParts() {
        let docsOnly = RetrievalInfo(documentCount: 4, contextCount: 4, kgClaimsUsed: 0, kgEntitiesUsed: 0)
        XCTAssertEqual(docsOnly.summary, "Searched library · 4 documents")
    }

    func testRetrievalRoundTripsThroughChatMessageCoding() throws {
        let message = ChatMessage(
            role: .assistant,
            content: "answer",
            retrieval: RetrievalInfo(documentCount: 2, contextCount: 2, kgClaimsUsed: 1, kgEntitiesUsed: 0)
        )
        let data = try JSONEncoder().encode(message)
        let decoded = try JSONDecoder().decode(ChatMessage.self, from: data)
        XCTAssertEqual(decoded.retrieval?.documentCount, 2)
        XCTAssertEqual(decoded.retrieval?.summary, "Searched library · 2 documents · 1 claim")
    }
}
