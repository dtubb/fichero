@testable import Fichero
import XCTest

/// `ChatAPIResponse.tool_calls` wiring (#1847/#2067): the engine's agent loop
/// emits `tool_calls[]` on every chat turn; the response type must surface
/// them (so `sendMessage` can attach them to the assistant `ChatMessage` and
/// `ToolCallCard` renders them) and stay back-compatible with payloads that
/// omit the field.
final class ChatAPIResponseToolCallsTests: XCTestCase {

    private func decode(_ json: String) throws -> ChatAPIResponse {
        try JSONDecoder().decode(ChatAPIResponse.self, from: Data(json.utf8))
    }

    func testDecodesWithoutToolCallsAsEmpty() throws {
        // Single-shot RAG path / older engines: no tool_calls key at all.
        let response = try decode("""
        {
          "message": "plain answer",
          "sources": [],
          "conversation_id": "c1"
        }
        """)

        XCTAssertEqual(response.toolCalls, [])
        XCTAssertEqual(response.message, "plain answer")
    }

    func testDecodesAuditedToolCallFromSnakeCase() throws {
        let response = try decode("""
        {
          "message": "grounded answer",
          "sources": [],
          "conversation_id": "c1",
          "tool_calls": [
            {
              "id": "t1",
              "action_name": "search.query",
              "actor": "chat",
              "audit_id": "audit-9",
              "is_mutation": false,
              "status": "ok",
              "params": {"query": "ada lovelace"}
            }
          ]
        }
        """)

        XCTAssertEqual(response.toolCalls.count, 1)
        let call = try XCTUnwrap(response.toolCalls.first)
        XCTAssertEqual(call.actionName, "search.query")
        XCTAssertEqual(call.actor, "chat")
        XCTAssertEqual(call.auditId, "audit-9")
        XCTAssertEqual(call.isMutation, false)
        XCTAssertEqual(call.status, .succeeded)
        XCTAssertEqual(call.params?["query"]?.value as? String, "ada lovelace")
    }

    func testDeniedMutationSurfacesAsErrorStatus() throws {
        // A refused mutating call is recorded (status error, is_mutation true,
        // no audit id) — never silently dropped from the payload.
        let response = try decode("""
        {
          "message": "acknowledged",
          "sources": [],
          "conversation_id": "c1",
          "tool_calls": [
            {
              "id": "t2",
              "action_name": "document.delete",
              "actor": "chat",
              "is_mutation": true,
              "status": "error"
            }
          ]
        }
        """)

        let call = try XCTUnwrap(response.toolCalls.first)
        XCTAssertEqual(call.status, .error)
        XCTAssertEqual(call.isMutation, true)
        XCTAssertNil(call.auditId)
    }
}
