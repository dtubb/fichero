@testable import Fichero
import XCTest

final class ChatAPIResponseTests: XCTestCase {
    func testDecodesTelemetryAndModelWireKeys() throws {
        let response = try JSONDecoder().decode(
            ChatAPIResponse.self,
            from: Data(#"{"message":"answer","sources":[],"conversation_id":"c-1","model_used":"gpt","document_count":2,"context_count":3,"kg_claims_used":4,"kg_entities_used":5}"#.utf8)
        )

        XCTAssertEqual(response.message, "answer")
        XCTAssertEqual(response.conversationId, "c-1")
        XCTAssertEqual(response.modelUsed, "gpt")
        XCTAssertEqual(response.documentCount, 2)
        XCTAssertEqual(response.contextCount, 3)
        XCTAssertEqual(response.kgClaimsUsed, 4)
        XCTAssertEqual(response.kgEntitiesUsed, 5)
    }
}
