@testable import Fichero
import XCTest

/// The ToolCall spine (#3 agentic-surface consolidation, migration step 3a).
/// Guards the two invariants the UI leans on: `tool_calls` decodes as an
/// optional on `ChatMessage` (nil against today's RAG /api/chat, present when
/// the engine wires the agentic loop), and the audited/params display helpers.
final class ToolCallTests: XCTestCase {

    // MARK: - ChatMessage.tool_calls is optional + back-compatible

    func testChatMessageDecodesWithoutToolCalls() throws {
        // Today's shape: the backend persists only id/role/content/timestamp.
        let json = """
        {"id": "m1", "role": "assistant", "content": "hi", "timestamp": 0}
        """.data(using: .utf8)!

        let message = try JSONDecoder().decode(ChatMessage.self, from: json)

        XCTAssertNil(message.toolCalls)
        XCTAssertEqual(message.content, "hi")
    }

    func testChatMessageDecodesToolCallsFromSnakeCase() throws {
        // Tomorrow's shape: the agentic loop attaches tool_calls[].
        let json = """
        {
          "id": "m2", "role": "assistant", "content": "moved it", "timestamp": 0,
          "tool_calls": [
            {"id": "t1", "action_name": "document.move", "actor": "chat",
             "audit_id": "a-99", "status": "ok",
             "params": {"node_id": 42}}
          ]
        }
        """.data(using: .utf8)!

        let message = try JSONDecoder().decode(ChatMessage.self, from: json)

        XCTAssertEqual(message.toolCalls?.count, 1)
        let call = try XCTUnwrap(message.toolCalls?.first)
        XCTAssertEqual(call.actionName, "document.move")
        XCTAssertEqual(call.actor, "chat")
        XCTAssertEqual(call.auditId, "a-99")
        XCTAssertEqual(call.status, .ok)
    }

    // MARK: - Display helpers

    func testIsAuditedReflectsAuditId() {
        XCTAssertTrue(ToolCall(actionName: "x", actor: "chat", auditId: "a-1").isAudited)
        XCTAssertFalse(ToolCall(actionName: "x", actor: "chat").isAudited)
        XCTAssertFalse(ToolCall(actionName: "x", actor: "chat", auditId: "").isAudited)
    }

    func testUnrecordedMutationOnlyFiresForKnownWrites() {
        // Known write, no record → raise.
        XCTAssertTrue(ToolCall(actionName: "w", actor: "chat", isMutation: true).isUnrecordedMutation)
        // Known write, recorded → fine.
        XCTAssertFalse(ToolCall(actionName: "w", actor: "chat", auditId: "a", isMutation: true).isUnrecordedMutation)
        // A read with no record → never cry wolf.
        XCTAssertFalse(ToolCall(actionName: "r", actor: "chat", isMutation: false).isUnrecordedMutation)
        // Unknown mutation-ness (today's engine) → don't cry wolf.
        XCTAssertFalse(ToolCall(actionName: "r", actor: "chat").isUnrecordedMutation)
    }

    func testParamsSummaryIsSortedAndStable() {
        let call = ToolCall(
            actionName: "document.move",
            params: ["target": AnyCodable("/Inbox"), "node_id": AnyCodable(42)],
            actor: "chat"
        )
        // Keys sorted → deterministic regardless of dict ordering.
        XCTAssertEqual(call.paramsSummary, "node_id: 42 · target: /Inbox")
    }

    func testParamsSummaryEmptyWhenNoParams() {
        XCTAssertEqual(ToolCall(actionName: "x", actor: "chat").paramsSummary, "")
    }
}
