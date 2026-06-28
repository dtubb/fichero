//
//  WorkflowStreamParsingTests.swift
//  FicheroTests
//
//  Tests for WorkflowStreamService.parseEvent() — SSE event parsing logic.
//  This is pure-function testing: JSON string in → WorkflowStreamEvent out.
//

import FicheroAPIClient
import Foundation
import Testing
@testable import Fichero

@MainActor
struct WorkflowStreamParsingTests {

    // MARK: - Helper

    private func makeService() -> WorkflowStreamService {
        WorkflowStreamService(ficheroClient: FicheroClient())
    }

    private func json(
        event: String,
        threadId: String = "thread-123",
        workflowId: String = "wf-456",
        data: [String: Any] = [:],
        extra: [String: Any] = [:]
    ) -> String {
        var dict: [String: Any] = [
            "event": event,
            "thread_id": threadId,
            "workflow_id": workflowId,
            "data": data,
            "timestamp": "2026-02-22T12:00:00Z"
        ]
        for (key, value) in extra {
            dict[key] = value
        }
        guard let jsonData = try? JSONSerialization.data(withJSONObject: dict) else {
            fatalError("Failed to encode test SSE payload")
        }
        guard let jsonString = String(bytes: jsonData, encoding: .utf8) else {
            fatalError("Failed to decode test SSE payload")
        }
        return jsonString
    }

    // MARK: - Start Event

    @Test("Parse start event with workflow name")
    func parseStartEvent() {
        let service = makeService()
        let input = json(event: "start", data: ["workflow_name": "My Workflow"])

        let result = service.parseEvent(input)

        if case .start(let threadId, let workflowName) = result {
            #expect(threadId == "thread-123")
            #expect(workflowName == "My Workflow")
        } else {
            Issue.record("Expected .start event, got \(String(describing: result))")
        }
    }

    @Test("Parse start event without workflow name defaults to Unknown")
    func parseStartEventNoName() {
        let service = makeService()
        let input = json(event: "start", data: [:])

        let result = service.parseEvent(input)

        if case .start(_, let workflowName) = result {
            #expect(workflowName == "Unknown")
        } else {
            Issue.record("Expected .start event, got \(String(describing: result))")
        }
    }

    // MARK: - Node Begin

    @Test("Parse node_begin with node_id in data dict")
    func parseNodeBeginFromData() {
        let service = makeService()
        let input = json(event: "node_begin", data: ["node_id": "node-1", "node_name": "Transcribe"])

        let result = service.parseEvent(input)

        if case .nodeBegin(let threadId, let nodeId, let nodeName) = result {
            #expect(threadId == "thread-123")
            #expect(nodeId == "node-1")
            #expect(nodeName == "Transcribe")
        } else {
            Issue.record("Expected .nodeBegin event, got \(String(describing: result))")
        }
    }

    @Test("Parse node_begin with top-level node_id")
    func parseNodeBeginTopLevel() {
        let service = makeService()
        let input = json(event: "node_begin", data: ["node_name": "Echo"], extra: ["node_id": "node-top"])

        let result = service.parseEvent(input)

        if case .nodeBegin(_, let nodeId, let nodeName) = result {
            #expect(nodeId == "node-top")
            #expect(nodeName == "Echo")
        } else {
            Issue.record("Expected .nodeBegin event, got \(String(describing: result))")
        }
    }

    // MARK: - Node End

    @Test("Parse node_end with duration")
    func parseNodeEnd() {
        let service = makeService()
        let input = json(event: "node_end", data: ["node_id": "node-1", "duration_ms": 1234.5])

        let result = service.parseEvent(input)

        if case .nodeEnd(let threadId, let nodeId, let durationMs, _) = result {
            #expect(threadId == "thread-123")
            #expect(nodeId == "node-1")
            #expect(durationMs == 1234.5)
        } else {
            Issue.record("Expected .nodeEnd event, got \(String(describing: result))")
        }
    }

    // MARK: - Complete

    @Test("Parse complete event with checkpoint_id")
    func parseComplete() {
        let service = makeService()
        let input = json(event: "complete", data: ["checkpoint_id": "cp-789"])

        let result = service.parseEvent(input)

        if case .complete(let threadId, let checkpointId, _) = result {
            #expect(threadId == "thread-123")
            #expect(checkpointId == "cp-789")
        } else {
            Issue.record("Expected .complete event, got \(String(describing: result))")
        }
    }

    @Test("Parse complete event without checkpoint_id")
    func parseCompleteNoCheckpoint() {
        let service = makeService()
        let input = json(event: "complete", data: [:])

        let result = service.parseEvent(input)

        if case .complete(_, let checkpointId, _) = result {
            #expect(checkpointId == nil)
        } else {
            Issue.record("Expected .complete event, got \(String(describing: result))")
        }
    }

    // MARK: - Pause

    @Test("Parse pause event")
    func parsePause() {
        let service = makeService()
        let input = json(event: "pause", data: ["checkpoint_id": "cp-pause"])

        let result = service.parseEvent(input)

        if case .pause(let threadId, let checkpointId, _) = result {
            #expect(threadId == "thread-123")
            #expect(checkpointId == "cp-pause")
        } else {
            Issue.record("Expected .pause event, got \(String(describing: result))")
        }
    }

    // MARK: - Error

    @Test("Parse error event")
    func parseError() {
        let service = makeService()
        let input = json(event: "error", data: ["error": "Something went wrong"])

        let result = service.parseEvent(input)

        if case .error(let threadId, let error) = result {
            #expect(threadId == "thread-123")
            #expect(error == "Something went wrong")
        } else {
            Issue.record("Expected .error event, got \(String(describing: result))")
        }
    }

    @Test("Parse error event without message defaults to Unknown error")
    func parseErrorNoMessage() {
        let service = makeService()
        let input = json(event: "error", data: [:])

        let result = service.parseEvent(input)

        if case .error(_, let error) = result {
            #expect(error == "Unknown error")
        } else {
            Issue.record("Expected .error event, got \(String(describing: result))")
        }
    }

    // MARK: - Parallel Events

    @Test("Parse parallel_start event")
    func parseParallelStart() {
        let service = makeService()
        let input = json(event: "parallel_start", data: ["total": 5], extra: ["node_id": "node-par"])

        let result = service.parseEvent(input)

        if case .parallelStart(let threadId, let nodeId, let fileTotal) = result {
            #expect(threadId == "thread-123")
            #expect(nodeId == "node-par")
            #expect(fileTotal == 5)
        } else {
            Issue.record("Expected .parallelStart event, got \(String(describing: result))")
        }
    }

    @Test("Parse file_start event with top-level fields")
    func parseFileStart() {
        let service = makeService()
        let input = json(
            event: "file_start",
            data: [:],
            extra: [
                "node_id": "node-1",
                "file_path": "/docs/test.pdf",
                "file_index": 2,
                "file_total": 10,
                "progress": 0.2,
                "document_id": "pdf-1",
                "page_id": "page-2",
                "display_name": "Page 2",
                "sequence": 2
            ]
        )

        let result = service.parseEvent(input)

        if case .fileStart(
            _, let nodeId, let filePath, let fileIndex, let fileTotal, let progress,
            let documentId, let pageId, let displayName, let sequence
        ) = result {
            #expect(nodeId == "node-1")
            #expect(filePath == "/docs/test.pdf")
            #expect(fileIndex == 2)
            #expect(fileTotal == 10)
            #expect(progress == 0.2)
            #expect(documentId == "pdf-1")
            #expect(pageId == "page-2")
            #expect(displayName == "Page 2")
            #expect(sequence == 2)
        } else {
            Issue.record("Expected .fileStart event, got \(String(describing: result))")
        }
    }

    @Test("Parse file_complete event")
    func parseFileComplete() {
        let service = makeService()
        let input = json(
            event: "file_complete",
            data: [:],
            extra: [
                "node_id": "node-1",
                "file_path": "/docs/done.pdf",
                "file_index": 3,
                "file_total": 10,
                "progress": 0.3,
                "document_id": "pdf-1",
                "page_id": "page-3",
                "display_name": "Page 3",
                "sequence": 3
            ]
        )

        let result = service.parseEvent(input)

        if case .fileComplete(
            _, let nodeId, let filePath, let fileIndex, let fileTotal, let progress, _,
            let documentId, let pageId, let displayName, let sequence
        ) = result {
            #expect(nodeId == "node-1")
            #expect(filePath == "/docs/done.pdf")
            #expect(fileIndex == 3)
            #expect(fileTotal == 10)
            #expect(progress == 0.3)
            #expect(documentId == "pdf-1")
            #expect(pageId == "page-3")
            #expect(displayName == "Page 3")
            #expect(sequence == 3)
        } else {
            Issue.record("Expected .fileComplete event, got \(String(describing: result))")
        }
    }

    @Test("Parse file_error event")
    func parseFileError() {
        let service = makeService()
        let input = json(
            event: "file_error",
            data: ["error": "File corrupt"],
            extra: [
                "node_id": "node-1",
                "file_path": "/docs/bad.pdf",
                "progress": 0.5,
                "document_id": "pdf-1",
                "page_id": "page-4",
                "display_name": "Page 4",
                "sequence": 4
            ]
        )

        let result = service.parseEvent(input)

        if case .fileError(
            _, let nodeId, let filePath, let error, let progress,
            let documentId, let pageId, let displayName, let sequence
        ) = result {
            #expect(nodeId == "node-1")
            #expect(filePath == "/docs/bad.pdf")
            #expect(error == "File corrupt")
            #expect(progress == 0.5)
            #expect(documentId == "pdf-1")
            #expect(pageId == "page-4")
            #expect(displayName == "Page 4")
            #expect(sequence == 4)
        } else {
            Issue.record("Expected .fileError event, got \(String(describing: result))")
        }
    }

    @Test("Parse parallel_complete event")
    func parseParallelComplete() {
        let service = makeService()
        let input = json(
            event: "parallel_complete",
            data: ["success_count": 8, "error_count": 2],
            extra: ["node_id": "node-par", "file_total": 10]
        )

        let result = service.parseEvent(input)

        if case .parallelComplete(_, let nodeId, let successCount, let errorCount, let total) = result {
            #expect(nodeId == "node-par")
            #expect(successCount == 8)
            #expect(errorCount == 2)
            #expect(total == 10)
        } else {
            Issue.record("Expected .parallelComplete event, got \(String(describing: result))")
        }
    }

    // MARK: - Systemic Error

    @Test("Parse systemic_error event")
    func parseSystemicError() {
        let service = makeService()
        let input = json(
            event: "systemic_error",
            data: ["error": "Too many failures", "error_count": 5, "total_count": 10]
        )

        let result = service.parseEvent(input)

        if case .systemicError(let threadId, let error, let errorCount, let totalCount) = result {
            #expect(threadId == "thread-123")
            #expect(error == "Too many failures")
            #expect(errorCount == 5)
            #expect(totalCount == 10)
        } else {
            Issue.record("Expected .systemicError event, got \(String(describing: result))")
        }
    }

    // MARK: - Log

    @Test("Parse log event")
    func parseLogEvent() {
        let service = makeService()
        let input = json(event: "log", data: ["line": "Processing document..."])

        let result = service.parseEvent(input)

        if case .log(let threadId, let line) = result {
            #expect(threadId == "thread-123")
            #expect(line == "Processing document...")
        } else {
            Issue.record("Expected .log event, got \(String(describing: result))")
        }
    }

    // MARK: - Edge Cases

    @Test("Unknown event type returns nil")
    func parseUnknownEvent() {
        let service = makeService()
        let input = json(event: "unknown_event_type", data: [:])

        let result = service.parseEvent(input)
        #expect(result == nil)
    }

    @Test("Invalid JSON returns nil")
    func parseInvalidJson() {
        let service = makeService()

        let result = service.parseEvent("this is not json")
        #expect(result == nil)
    }

    @Test("Empty string returns nil")
    func parseEmptyString() {
        let service = makeService()

        let result = service.parseEvent("")
        #expect(result == nil)
    }
}

// MARK: - AnyCodableValue Extension Tests

struct AnyCodableValueTests {

    @Test("stringValue extracts string")
    func stringValueExtractsString() {
        let value = AnyCodableValue.string("hello")
        #expect(value.stringValue == "hello")
    }

    @Test("stringValue returns nil for non-string")
    func stringValueReturnsNilForInt() {
        let value = AnyCodableValue.int(42)
        #expect(value.stringValue == nil)
    }

    @Test("doubleValue extracts double")
    func doubleValueExtractsDouble() {
        let value = AnyCodableValue.double(3.14)
        #expect(value.doubleValue == 3.14)
    }

    @Test("doubleValue converts int to double")
    func doubleValueConvertsInt() {
        let value = AnyCodableValue.int(42)
        #expect(value.doubleValue == 42.0)
    }

    @Test("doubleValue returns nil for string")
    func doubleValueReturnsNilForString() {
        let value = AnyCodableValue.string("not a number")
        #expect(value.doubleValue == nil)
    }

    @Test("intValue extracts int")
    func intValueExtractsInt() {
        let value = AnyCodableValue.int(99)
        #expect(value.intValue == 99)
    }

    @Test("intValue converts double to int")
    func intValueConvertsDouble() {
        let value = AnyCodableValue.double(7.0)
        #expect(value.intValue == 7)
    }

    @Test("intValue returns nil for string")
    func intValueReturnsNilForString() {
        let value = AnyCodableValue.string("nope")
        #expect(value.intValue == nil)
    }
}

// MARK: - SSEEventData Decoding Tests

struct SSEEventDataDecodingTests {

    @Test("Decode minimal SSE event data")
    func decodeMinimalEvent() throws {
        let json = Data("""
        {
            "event": "start",
            "thread_id": "t-1",
            "workflow_id": "w-1",
            "data": {"workflow_name": "Test"},
            "timestamp": "2026-02-22T12:00:00Z"
        }
        """.utf8)

        let event = try JSONDecoder().decode(SSEEventData.self, from: json)
        #expect(event.event == "start")
        #expect(event.threadId == "t-1")
        #expect(event.workflowId == "w-1")
        #expect(event.nodeId == nil)
        #expect(event.filePath == nil)
        #expect(event.fileIndex == nil)
        #expect(event.fileTotal == nil)
        #expect(event.progress == nil)
    }

    @Test("Decode SSE event with all parallel fields")
    func decodeParallelFields() throws {
        let json = Data("""
        {
            "event": "file_start",
            "thread_id": "t-1",
            "workflow_id": "w-1",
            "data": {},
            "timestamp": "2026-02-22T12:00:00Z",
            "node_id": "node-1",
            "file_path": "/test.pdf",
            "file_index": 2,
            "file_total": 10,
            "progress": 0.2
        }
        """.utf8)

        let event = try JSONDecoder().decode(SSEEventData.self, from: json)
        #expect(event.nodeId == "node-1")
        #expect(event.filePath == "/test.pdf")
        #expect(event.fileIndex == 2)
        #expect(event.fileTotal == 10)
        #expect(event.progress == 0.2)
    }

    @Test("Decode SSE event with nested data values")
    func decodeNestedData() throws {
        let json = Data("""
        {
            "event": "node_end",
            "thread_id": "t-1",
            "workflow_id": "w-1",
            "data": {
                "node_id": "node-abc",
                "duration_ms": 500.5
            },
            "timestamp": "2026-02-22T12:00:00Z"
        }
        """.utf8)

        let event = try JSONDecoder().decode(SSEEventData.self, from: json)
        #expect(event.data["node_id"]?.stringValue == "node-abc")
        #expect(event.data["duration_ms"]?.doubleValue == 500.5)
    }
}

// MARK: - ExecuteAcceptedResponse Tests

struct ExecuteAcceptedResponseTests {

    @Test("Decode execute accepted response")
    func decodeResponse() throws {
        let json = Data("""
        {
            "thread_id": "t-abc",
            "workflow_id": "w-123",
            "workflow_name": "My Workflow",
            "status": "running",
            "stream_url": "/api/stream/t-abc"
        }
        """.utf8)

        let response = try JSONDecoder().decode(ExecuteAcceptedResponse.self, from: json)
        #expect(response.threadId == "t-abc")
        #expect(response.workflowId == "w-123")
        #expect(response.workflowName == "My Workflow")
        #expect(response.status == "running")
        #expect(response.streamUrl == "/api/stream/t-abc")
    }
}
