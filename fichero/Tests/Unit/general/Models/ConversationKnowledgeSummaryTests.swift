@testable import Fichero
import XCTest

/// The Knowledge-tab summary (#3, step 5). Pure aggregation over per-message
/// RetrievalInfo — the tractable thing to test.
final class ConversationKnowledgeSummaryTests: XCTestCase {

    private func retrieval(entities: Int, claims: Int) -> RetrievalInfo {
        RetrievalInfo(documentCount: 0, contextCount: 0, kgClaimsUsed: claims, kgEntitiesUsed: entities)
    }

    func testAggregatesOnlyRepliesThatUsedKnowledge() {
        let conversation = Conversation(messages: [
            ChatMessage(role: .user, content: "q"),
            ChatMessage(role: .assistant, content: "a", retrieval: retrieval(entities: 3, claims: 1)),
            ChatMessage(role: .assistant, content: "b", retrieval: retrieval(entities: 0, claims: 0)), // searched docs only
            ChatMessage(role: .assistant, content: "c", retrieval: retrieval(entities: 2, claims: 4))
        ])

        let summary = ConversationKnowledgeSummary.summarize(conversation)

        XCTAssertEqual(summary.repliesWithKnowledge, 2)
        XCTAssertEqual(summary.entityReferences, 5)
        XCTAssertEqual(summary.claimReferences, 5)
        XCTAssertFalse(summary.isEmpty)
    }

    func testEmptyWhenNoRetrieval() {
        let conversation = Conversation(messages: [
            ChatMessage(role: .user, content: "hi"),
            ChatMessage(role: .assistant, content: "hello")
        ])
        XCTAssertTrue(ConversationKnowledgeSummary.summarize(conversation).isEmpty)
    }
}
