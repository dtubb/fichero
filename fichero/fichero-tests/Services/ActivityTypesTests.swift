//
//  ActivityTypesTests.swift
//  FicheroTests
//
//  Tests for ActivityTypes: AnyValueAsString encoding/decoding,
//  ActivityItem Codable roundtrip, computed properties, and ActivityStats.
//

import Foundation
import Testing
@testable import Fichero

// MARK: - AnyValueAsString Tests

struct AnyValueAsStringTests {

    @Test("Decode string value")
    func decodeString() throws {
        let json = Data(#""hello""#.utf8)
        let result = try JSONDecoder().decode(AnyValueAsString.self, from: json)
        #expect(result.value == "hello")
    }

    @Test("Decode integer value as string")
    func decodeInt() throws {
        let json = Data("42".utf8)
        let result = try JSONDecoder().decode(AnyValueAsString.self, from: json)
        #expect(result.value == "42")
    }

    @Test("Decode double value as string")
    func decodeDouble() throws {
        let json = Data("3.14".utf8)
        let result = try JSONDecoder().decode(AnyValueAsString.self, from: json)
        #expect(result.value == "3.14")
    }

    @Test("Decode bool value as string")
    func decodeBool() throws {
        let json = Data("true".utf8)
        let result = try JSONDecoder().decode(AnyValueAsString.self, from: json)
        #expect(result.value == "true")
    }

    @Test("Decode null/unsupported value as empty string")
    func decodeNull() throws {
        let json = Data("null".utf8)
        let result = try JSONDecoder().decode(AnyValueAsString.self, from: json)
        #expect(result.value == "")
    }

    @Test("Encode always produces string")
    func encodeAsString() throws {
        let value = AnyValueAsString("42")
        let data = try JSONEncoder().encode(value)
        let str = String(data: data, encoding: .utf8)
        #expect(str == #""42""#)
    }

    @Test("Init with string value directly")
    func initDirect() {
        let value = AnyValueAsString("test")
        #expect(value.value == "test")
    }

    @Test("Roundtrip encode/decode preserves value")
    func roundtrip() throws {
        let original = AnyValueAsString("roundtrip-value")
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(AnyValueAsString.self, from: data)
        #expect(decoded.value == original.value)
    }
}

// MARK: - ActivityItem Tests

struct ActivityItemTests {

    private func sampleJSON(
        extraFields: [String: Any] = [:]
    ) -> Data {
        var dict: [String: Any] = [
            "id": "act-001",
            "type": "workflow_started",
            "level": "info",
            "timestamp": "2026-02-22T12:00:00Z",
            "message": "Workflow started successfully",
            "workflow_id": "wf-123",
            "batch_id": "batch-456",
            "thread_id": "thread-789",
            "node_id": "node-abc",
            "metadata": ["key1": "value1", "key2": 42],
            "duration_ms": 1500.5,
            "error": nil as Any? as Any
        ]
        for (key, value) in extraFields {
            dict[key] = value
        }
        return try! JSONSerialization.data(withJSONObject: dict)
    }

    @Test("Decode full ActivityItem from JSON")
    func decodeFull() throws {
        let item = try JSONDecoder().decode(ActivityItem.self, from: sampleJSON())

        #expect(item.id == "act-001")
        #expect(item.type == "workflow_started")
        #expect(item.level == "info")
        #expect(item.timestamp == "2026-02-22T12:00:00Z")
        #expect(item.message == "Workflow started successfully")
        #expect(item.workflowId == "wf-123")
        #expect(item.batchId == "batch-456")
        #expect(item.threadId == "thread-789")
        #expect(item.nodeId == "node-abc")
        #expect(item.durationMs == 1500.5)
        #expect(item.error == nil)
    }

    @Test("Metadata maps AnyValueAsString to plain strings")
    func metadataMapping() throws {
        let item = try JSONDecoder().decode(ActivityItem.self, from: sampleJSON())
        let meta = item.metadataStrings
        #expect(meta?["key1"] == "value1")
        #expect(meta?["key2"] == "42")
    }

    @Test("Decode minimal ActivityItem (only required fields)")
    func decodeMinimal() throws {
        let json: [String: Any] = [
            "id": "act-002",
            "type": "node_started",
            "level": "debug",
            "timestamp": "2026-01-01T00:00:00Z",
            "message": "Node started"
        ]
        let data = try JSONSerialization.data(withJSONObject: json)
        let item = try JSONDecoder().decode(ActivityItem.self, from: data)

        #expect(item.id == "act-002")
        #expect(item.workflowId == nil)
        #expect(item.batchId == nil)
        #expect(item.metadata == nil)
        #expect(item.durationMs == nil)
    }

    // MARK: - parsedTimestamp

    @Test("Parse ISO8601 timestamp with fractional seconds")
    func parsedTimestampISO8601Fractional() {
        let item = ActivityItem(
            id: "t1", type: "test", level: "info",
            timestamp: "2026-02-22T12:30:45.123Z",
            message: "test"
        )
        #expect(item.parsedTimestamp != nil)
    }

    @Test("Parse ISO8601 timestamp without fractional seconds")
    func parsedTimestampISO8601NoFraction() {
        let item = ActivityItem(
            id: "t2", type: "test", level: "info",
            timestamp: "2026-02-22T12:30:45Z",
            message: "test"
        )
        #expect(item.parsedTimestamp != nil)
    }

    @Test("Parse timestamp with microseconds (no timezone)")
    func parsedTimestampMicroseconds() {
        let item = ActivityItem(
            id: "t3", type: "test", level: "info",
            timestamp: "2026-02-22T12:30:45.123456",
            message: "test"
        )
        #expect(item.parsedTimestamp != nil)
    }

    @Test("Parse timestamp with milliseconds (no timezone)")
    func parsedTimestampMilliseconds() {
        let item = ActivityItem(
            id: "t4", type: "test", level: "info",
            timestamp: "2026-02-22T12:30:45.123",
            message: "test"
        )
        #expect(item.parsedTimestamp != nil)
    }

    @Test("Parse timestamp without fractional seconds (no timezone)")
    func parsedTimestampPlain() {
        let item = ActivityItem(
            id: "t5", type: "test", level: "info",
            timestamp: "2026-02-22T12:30:45",
            message: "test"
        )
        #expect(item.parsedTimestamp != nil)
    }

    @Test("Invalid timestamp returns nil")
    func parsedTimestampInvalid() {
        let item = ActivityItem(
            id: "t6", type: "test", level: "info",
            timestamp: "not-a-date",
            message: "test"
        )
        #expect(item.parsedTimestamp == nil)
    }

    // MARK: - levelColor

    @Test("Level color for error")
    func levelColorError() {
        let item = ActivityItem(id: "l1", type: "t", level: "error", timestamp: "", message: "")
        #expect(item.levelColor == "red")
    }

    @Test("Level color for critical")
    func levelColorCritical() {
        let item = ActivityItem(id: "l2", type: "t", level: "critical", timestamp: "", message: "")
        #expect(item.levelColor == "red")
    }

    @Test("Level color for warning")
    func levelColorWarning() {
        let item = ActivityItem(id: "l3", type: "t", level: "warning", timestamp: "", message: "")
        #expect(item.levelColor == "orange")
    }

    @Test("Level color for info")
    func levelColorInfo() {
        let item = ActivityItem(id: "l4", type: "t", level: "info", timestamp: "", message: "")
        #expect(item.levelColor == "blue")
    }

    @Test("Level color for debug")
    func levelColorDebug() {
        let item = ActivityItem(id: "l5", type: "t", level: "debug", timestamp: "", message: "")
        #expect(item.levelColor == "gray")
    }

    @Test("Level color for unknown level")
    func levelColorUnknown() {
        let item = ActivityItem(id: "l6", type: "t", level: "trace", timestamp: "", message: "")
        #expect(item.levelColor == "primary")
    }

    // MARK: - typeIcon

    @Test("Type icon for workflow types")
    func typeIconWorkflow() {
        let cases: [(String, String)] = [
            ("workflow_started", "play.circle"),
            ("workflow_completed", "checkmark.circle"),
            ("workflow_failed", "xmark.circle"),
            ("workflow_paused", "pause.circle"),
            ("workflow_resumed", "play.circle"),
            ("workflow_cancelled", "stop.circle"),
        ]
        for (type, expected) in cases {
            let item = ActivityItem(id: "i", type: type, level: "info", timestamp: "", message: "")
            #expect(item.typeIcon == expected, "Expected \(expected) for type \(type)")
        }
    }

    @Test("Type icon for node types")
    func typeIconNode() {
        let cases: [(String, String)] = [
            ("node_started", "circle.dashed"),
            ("node_completed", "circle.fill"),
            ("node_failed", "exclamationmark.circle"),
        ]
        for (type, expected) in cases {
            let item = ActivityItem(id: "i", type: type, level: "info", timestamp: "", message: "")
            #expect(item.typeIcon == expected, "Expected \(expected) for type \(type)")
        }
    }

    @Test("Type icon for unknown type returns circle")
    func typeIconUnknown() {
        let item = ActivityItem(id: "i", type: "custom_event", level: "info", timestamp: "", message: "")
        #expect(item.typeIcon == "circle")
    }

    // MARK: - status

    @Test("Status derived from running types")
    func statusRunning() {
        for type in ["workflow_started", "node_started", "batch_started"] {
            let item = ActivityItem(id: "s", type: type, level: "info", timestamp: "", message: "")
            #expect(item.status == "running")
        }
    }

    @Test("Status derived from completed types")
    func statusCompleted() {
        for type in ["workflow_completed", "node_completed", "batch_completed", "batch_item_completed"] {
            let item = ActivityItem(id: "s", type: type, level: "info", timestamp: "", message: "")
            #expect(item.status == "completed")
        }
    }

    @Test("Status derived from failed types")
    func statusFailed() {
        for type in ["workflow_failed", "node_failed", "batch_item_failed"] {
            let item = ActivityItem(id: "s", type: type, level: "info", timestamp: "", message: "")
            #expect(item.status == "failed")
        }
    }

    @Test("Status for paused and cancelled")
    func statusPausedCancelled() {
        let paused = ActivityItem(id: "s", type: "workflow_paused", level: "info", timestamp: "", message: "")
        #expect(paused.status == "paused")

        let cancelled = ActivityItem(id: "s", type: "workflow_cancelled", level: "info", timestamp: "", message: "")
        #expect(cancelled.status == "cancelled")
    }

    @Test("Status defaults to level for unknown types")
    func statusFallback() {
        let item = ActivityItem(id: "s", type: "custom", level: "warning", timestamp: "", message: "")
        #expect(item.status == "warning")
    }

    // MARK: - name

    @Test("Name truncates long messages to 40 chars with ellipsis")
    func nameTruncation() {
        let longMessage = String(repeating: "a", count: 50)
        let item = ActivityItem(id: "n", type: "t", level: "info", timestamp: "", message: longMessage)
        #expect(item.name.hasSuffix("..."))
        #expect(item.name.count == 43) // 40 + "..."
    }

    @Test("Name uses full message when short")
    func nameShort() {
        let item = ActivityItem(id: "n", type: "t", level: "info", timestamp: "", message: "Short msg")
        #expect(item.name == "Short msg")
    }

    @Test("Name falls back to type when message is empty")
    func nameEmpty() {
        let item = ActivityItem(id: "n", type: "workflow_started", level: "info", timestamp: "", message: "")
        #expect(item.name == "workflow_started")
    }
}

// MARK: - ActivityStats Tests

struct ActivityStatsTests {

    @Test("Decode ActivityStats from JSON")
    func decodeStats() throws {
        let json: [String: Any] = [
            "total_activities": 100,
            "activities_by_type": ["workflow_started": 50, "workflow_completed": 50],
            "activities_by_level": ["info": 80, "error": 20],
            "error_count": 20,
            "warning_count": 5,
            "avg_workflow_duration_ms": 2500.0,
            "success_rate": 0.95,
            "period_start": "2026-01-01T00:00:00Z",
            "period_end": "2026-02-01T00:00:00Z"
        ]
        let data = try JSONSerialization.data(withJSONObject: json)
        let stats = try JSONDecoder().decode(ActivityStats.self, from: data)

        #expect(stats.totalActivities == 100)
        #expect(stats.errorCount == 20)
        #expect(stats.warningCount == 5)
        #expect(stats.successRate == 0.95)
        #expect(stats.avgWorkflowDurationMs == 2500.0)
        #expect(stats.activitiesByType["workflow_started"] == 50)
        #expect(stats.activitiesByLevel["info"] == 80)
    }

    @Test("Decode ActivityStats with null avgWorkflowDurationMs")
    func decodeStatsNullDuration() throws {
        let json: [String: Any] = [
            "total_activities": 0,
            "activities_by_type": [:] as [String: Any],
            "activities_by_level": [:] as [String: Any],
            "error_count": 0,
            "warning_count": 0,
            "success_rate": 0.0,
            "period_start": "2026-01-01T00:00:00Z",
            "period_end": "2026-02-01T00:00:00Z"
        ]
        let data = try JSONSerialization.data(withJSONObject: json)
        let stats = try JSONDecoder().decode(ActivityStats.self, from: data)

        #expect(stats.avgWorkflowDurationMs == nil)
    }
}
