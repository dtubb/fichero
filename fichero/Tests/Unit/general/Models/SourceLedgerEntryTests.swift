@testable import Fichero
import XCTest

/// The unified Source ledger (#3, migration step 3b). The builder is pure — it
/// derives "what the conversation cited" from message sources — so it is the
/// tractable thing to test.
final class SourceLedgerEntryTests: XCTestCase {

    private func doc(_ id: String, _ name: String) -> DocumentSource {
        DocumentSource(id: "s-\(id)", documentId: id, documentName: name, excerpt: "", relevanceScore: 0.5)
    }

    func testLedgerDedupesSameDocumentCitedTwice() {
        let conversation = Conversation(messages: [
            ChatMessage(role: .assistant, content: "a", sources: [doc("1", "Diary")]),
            ChatMessage(role: .assistant, content: "b", sources: [doc("1", "Diary"), doc("2", "Map")])
        ])

        let ledger = SourceLedgerEntry.ledger(for: conversation)

        // Doc 1 cited twice → one entry; order = first-cited.
        XCTAssertEqual(ledger.map(\.nodeId), ["1", "2"])
        XCTAssertTrue(ledger.allSatisfy { $0.kind == .document })
    }

    func testLedgerEmptyWhenNoSources() {
        let conversation = Conversation(messages: [
            ChatMessage(role: .user, content: "hi"),
            ChatMessage(role: .assistant, content: "hello")
        ])
        XCTAssertTrue(SourceLedgerEntry.ledger(for: conversation).isEmpty)
    }

    func testLedgerAppendsResearchSourcesAfterDocuments() {
        let conversation = Conversation(messages: [
            ChatMessage(role: .assistant, content: "a", sources: [doc("1", "Diary")])
        ])
        let research = ResearchSource(
            id: "r1", projectId: "p1", sourceType: "url",
            label: "LAC map", url: "https://example.org", description: "", createdAt: Date()
        )

        let ledger = SourceLedgerEntry.ledger(for: conversation, researchSources: [research])

        XCTAssertEqual(ledger.map(\.kind), [.document, .research])
        XCTAssertEqual(ledger.last?.detail, "https://example.org")
    }
}
