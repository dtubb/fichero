@testable import Fichero
import XCTest

/// Tests for the `Event` audit-log model. Has actual logic worth
/// verifying: event-type string parsing (`document.create` → action +
/// entity), canUndo predicate, source/action helpers, JSON round-trip
/// across Swift ↔ Python snake_case.
final class EventTests: XCTestCase {

    // MARK: - JSON round-trip

    func testEncodeDecodeRoundTrip() throws {
        let original = Event(
            id: "ev-1",
            eventType: "document.update",
            targetType: "Document",
            targetId: "doc-1",
            before: ["name": AnyCodable("old")],
            after: ["name": AnyCodable("new")],
            source: "user",
            runId: "r-1"
        )
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(Event.self, from: data)
        XCTAssertEqual(decoded.id, "ev-1")
        XCTAssertEqual(decoded.eventType, "document.update")
        XCTAssertEqual(decoded.targetId, "doc-1")
        XCTAssertEqual(decoded.runId, "r-1")
    }

    func testDecodesPythonSnakeCase() throws {
        let json = """
        {
            "id": "ev-1",
            "timestamp": "2026-05-10T12:00:00Z",
            "event_type": "artifact.create",
            "target_type": "Artifact",
            "target_id": "art-1",
            "before": null,
            "after": null,
            "source": "workflow",
            "run_id": "r-42",
            "metadata": {}
        }
        """.data(using: .utf8)!
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let ev = try decoder.decode(Event.self, from: json)
        XCTAssertEqual(ev.eventType, "artifact.create")
        XCTAssertEqual(ev.targetType, "Artifact")
        XCTAssertEqual(ev.runId, "r-42")
        XCTAssertEqual(ev.source, "workflow")
    }

    // MARK: - action / entity parsing

    func testActionParsedFromDottedEventType() {
        XCTAssertEqual(makeEvent(type: "document.create").action, "create")
        XCTAssertEqual(makeEvent(type: "artifact.update").action, "update")
        XCTAssertEqual(makeEvent(type: "workflow.delete").action, "delete")
        XCTAssertEqual(makeEvent(type: "document.move").action, "move")
    }

    func testEntityParsedFromDottedEventType() {
        XCTAssertEqual(makeEvent(type: "document.create").entity, "document")
        XCTAssertEqual(makeEvent(type: "artifact.update").entity, "artifact")
        XCTAssertEqual(makeEvent(type: "note.delete").entity, "note")
    }

    func testActionWithoutDotFallsBackToWholeString() {
        // Defensive: malformed event_type still produces something
        // safe — the whole string is treated as both action and entity.
        let ev = makeEvent(type: "unknown")
        XCTAssertEqual(ev.action, "unknown")
        XCTAssertEqual(ev.entity, "unknown")
    }

    // MARK: - display name / icon / color

    func testDisplayNameCapitalises() {
        XCTAssertEqual(
            makeEvent(type: "document.create").eventTypeDisplayName,
            "Document Create"
        )
        XCTAssertEqual(
            makeEvent(type: "artifact.update").eventTypeDisplayName,
            "Artifact Update"
        )
    }

    func testIconForKnownActions() {
        XCTAssertEqual(makeEvent(type: "x.create").eventTypeIcon, "plus.circle")
        XCTAssertEqual(makeEvent(type: "x.update").eventTypeIcon, "pencil.circle")
        XCTAssertEqual(makeEvent(type: "x.delete").eventTypeIcon, "trash.circle")
        XCTAssertEqual(makeEvent(type: "x.move").eventTypeIcon, "arrow.right.circle")
    }

    func testIconUnknownActionFallsBack() {
        XCTAssertEqual(
            makeEvent(type: "x.totally-unknown").eventTypeIcon,
            "info.circle"
        )
    }

    func testColorForKnownActions() {
        XCTAssertEqual(makeEvent(type: "x.create").eventTypeColor, "green")
        XCTAssertEqual(makeEvent(type: "x.update").eventTypeColor, "blue")
        XCTAssertEqual(makeEvent(type: "x.delete").eventTypeColor, "red")
        XCTAssertEqual(makeEvent(type: "x.move").eventTypeColor, "orange")
    }

    func testColorUnknownActionFallsBack() {
        XCTAssertEqual(
            makeEvent(type: "x.totally-unknown").eventTypeColor,
            "gray"
        )
    }

    // MARK: - canUndo

    func testCanUndoUpdateWithBeforeState() {
        let ev = Event(
            eventType: "document.update",
            targetType: "Document",
            targetId: "d",
            before: ["a": AnyCodable("b")]
        )
        XCTAssertTrue(ev.canUndo)
    }

    func testCanUndoDeleteWithBeforeState() {
        let ev = Event(
            eventType: "document.delete",
            targetType: "Document",
            targetId: "d",
            before: ["a": AnyCodable("b")]
        )
        XCTAssertTrue(ev.canUndo)
    }

    func testCanUndoCreateAlwaysFalse() {
        // Even if before is present, you don't "undo" a create — you
        // delete it. The semantic is correctly false here.
        let ev = Event(
            eventType: "document.create",
            targetType: "Document",
            targetId: "d",
            before: ["a": AnyCodable("b")]
        )
        XCTAssertFalse(ev.canUndo)
    }

    func testCanUndoUpdateWithoutBeforeIsFalse() {
        let ev = Event(
            eventType: "document.update",
            targetType: "Document",
            targetId: "d",
            before: nil
        )
        XCTAssertFalse(ev.canUndo)
    }

    // MARK: - source predicates

    func testIsUserEvent() {
        let user = Event(
            eventType: "x.update", targetType: "D", targetId: "d", source: "user"
        )
        let sys = Event(
            eventType: "x.update", targetType: "D", targetId: "d", source: "system"
        )
        XCTAssertTrue(user.isUserEvent)
        XCTAssertFalse(sys.isUserEvent)
    }

    func testIsWorkflowEvent() {
        let wf = Event(
            eventType: "x.update", targetType: "D", targetId: "d", source: "workflow"
        )
        let user = Event(
            eventType: "x.update", targetType: "D", targetId: "d", source: "user"
        )
        XCTAssertTrue(wf.isWorkflowEvent)
        XCTAssertFalse(user.isWorkflowEvent)
    }

    // MARK: - EventType enum

    func testEventTypeEnumActionAndEntity() {
        XCTAssertEqual(Event.EventType.documentCreate.action, "create")
        XCTAssertEqual(Event.EventType.documentCreate.entity, "document")
        XCTAssertEqual(Event.EventType.workflowDelete.action, "delete")
        XCTAssertEqual(Event.EventType.workflowDelete.entity, "workflow")
    }

    // MARK: - Helper

    private func makeEvent(type: String) -> Event {
        Event(
            eventType: type,
            targetType: "Document",
            targetId: "d"
        )
    }
}
