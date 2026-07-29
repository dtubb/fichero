@testable import Fichero
import Foundation
import XCTest

/// Tests for the Trace model — LangChain/LangGraph debug record.
/// Locks: snake_case keys (matches Python Trace model), trace-type
/// helpers (isLLMCall/isToolCall, display name, icon), token+duration
/// arithmetic, formatters for latency + cost, and the hasError flag.
final class TraceModelTests: XCTestCase {

    // MARK: - Init defaults

    func testInitDefaults() {
        let t = Trace(runId: "r-1", name: "step", traceType: "llm")
        XCTAssertFalse(t.id.isEmpty)            // UUID
        XCTAssertNil(t.parentTraceId)
        XCTAssertEqual(t.sequence, 0)
        XCTAssertEqual(t.status, "running")
        XCTAssertNil(t.error)
        XCTAssertEqual(t.tokensIn, 0)
        XCTAssertEqual(t.tokensOut, 0)
        XCTAssertEqual(t.costUsd, 0.0)
        XCTAssertTrue(t.metadata.isEmpty)
    }

    // MARK: - Snake_case decode

    func testTraceDecodesSnakeCase() throws {
        let json = """
        {
            "id": "t-1",
            "run_id": "r-1",
            "parent_trace_id": "t-parent",
            "sequence": 3,
            "name": "summarize",
            "trace_type": "llm",
            "status": "completed",
            "error": null,
            "inputs": {"prompt": "x"},
            "outputs": {"text": "y"},
            "started_at": "2026-05-11T08:00:00Z",
            "ended_at": "2026-05-11T08:00:01Z",
            "latency_ms": 1000,
            "model": "gpt-4o",
            "tokens_in": 100,
            "tokens_out": 50,
            "cost_usd": 0.01,
            "metadata": {}
        }
        """.data(using: .utf8)!
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let t = try decoder.decode(Trace.self, from: json)
        XCTAssertEqual(t.runId, "r-1")
        XCTAssertEqual(t.parentTraceId, "t-parent")
        XCTAssertEqual(t.traceType, "llm")
        XCTAssertEqual(t.latencyMs, 1000)
        XCTAssertEqual(t.tokensIn, 100)
        XCTAssertEqual(t.tokensOut, 50)
        XCTAssertEqual(t.costUsd, 0.01)
        XCTAssertEqual(t.model, "gpt-4o")
    }

    // MARK: - TraceType enum

    func testTraceTypeRawValuesStable() {
        XCTAssertEqual(Trace.TraceType.llm.rawValue, "llm")
        XCTAssertEqual(Trace.TraceType.chain.rawValue, "chain")
        XCTAssertEqual(Trace.TraceType.tool.rawValue, "tool")
        XCTAssertEqual(Trace.TraceType.retriever.rawValue, "retriever")
        XCTAssertEqual(Trace.TraceType.agent.rawValue, "agent")
    }

    // MARK: - isLLMCall / isToolCall

    func testIsLLMCallTrueForLLMType() {
        XCTAssertTrue(makeTrace(traceType: "llm").isLLMCall)
        XCTAssertFalse(makeTrace(traceType: "chain").isLLMCall)
    }

    func testIsToolCallTrueForToolType() {
        XCTAssertTrue(makeTrace(traceType: "tool").isToolCall)
        XCTAssertFalse(makeTrace(traceType: "agent").isToolCall)
    }

    // MARK: - Display name + icon

    func testTraceTypeDisplayName() {
        let pairs: [(String, String)] = [
            ("llm", "LLM Call"), ("chain", "Chain"),
            ("tool", "Tool"), ("retriever", "Retriever"),
            ("agent", "Agent"), ("custom", "Custom")  // fallback capitalised
        ]
        for (type, expected) in pairs {
            XCTAssertEqual(makeTrace(traceType: type).traceTypeDisplayName, expected, "type=\(type)")
        }
    }

    func testTraceTypeIcon() {
        let pairs: [(String, String)] = [
            ("llm", "brain"), ("chain", "link"),
            ("tool", "wrench"), ("retriever", "magnifyingglass"),
            ("agent", "person.circle"), ("garbage", "questionmark.circle")
        ]
        for (type, icon) in pairs {
            XCTAssertEqual(makeTrace(traceType: type).traceTypeIcon, icon, "type=\(type)")
        }
    }

    // MARK: - totalTokens

    func testTotalTokensSum() {
        let t = makeTrace(tokensIn: 100, tokensOut: 50)
        XCTAssertEqual(t.totalTokens, 150)
    }

    // MARK: - duration

    func testDurationComputedFromTimestamps() {
        let start = Date(timeIntervalSince1970: 0)
        let end = Date(timeIntervalSince1970: 2.5)
        let t = makeTrace(startedAt: start, endedAt: end)
        XCTAssertEqual(t.duration, 2.5)
    }

    func testDurationNilWhenNotEnded() {
        let t = makeTrace(endedAt: nil)
        XCTAssertNil(t.duration)
    }

    // MARK: - latencyString

    func testLatencyStringSubSecondUsesMs() {
        XCTAssertEqual(makeTrace(latencyMs: 250).latencyString, "250ms")
        XCTAssertEqual(makeTrace(latencyMs: 999).latencyString, "999ms")
    }

    func testLatencyStringSecondsAndAbove() {
        XCTAssertEqual(makeTrace(latencyMs: 1000).latencyString, "1.00s")
        XCTAssertEqual(makeTrace(latencyMs: 2500).latencyString, "2.50s")
    }

    func testLatencyStringNilWhenLatencyMissing() {
        XCTAssertNil(makeTrace(latencyMs: nil).latencyString)
    }

    // MARK: - costFormatted

    func testCostFormattedSixDecimals() {
        XCTAssertEqual(makeTrace(costUsd: 0.001234).costFormatted, "$0.001234")
        XCTAssertEqual(makeTrace(costUsd: 0).costFormatted, "$0.000000")
    }

    // MARK: - hasError

    func testHasErrorOnFailedStatus() {
        XCTAssertTrue(makeTrace(status: "failed").hasError)
    }

    func testHasErrorOnErrorMessage() {
        XCTAssertTrue(makeTrace(status: "completed", error: "boom").hasError)
    }

    func testHasErrorFalseOnNormalSuccess() {
        XCTAssertFalse(makeTrace(status: "completed", error: nil).hasError)
        XCTAssertFalse(makeTrace(status: "running", error: nil).hasError)
    }

    // MARK: - Hashable / Equatable

    func testTraceHashableByValue() {
        let a = makeTrace()
        let b = a  // value-type copy
        XCTAssertEqual(a, b)
        XCTAssertEqual(a.hashValue, b.hashValue)
    }

    // MARK: - Helpers

    private func makeTrace(
        traceType: String = "llm",
        status: String = "running",
        error: String? = nil,
        startedAt: Date = Date(timeIntervalSince1970: 0),
        endedAt: Date? = nil,
        latencyMs: Int? = nil,
        tokensIn: Int = 0,
        tokensOut: Int = 0,
        costUsd: Double = 0.0
    ) -> Trace {
        Trace(
            id: "t",
            runId: "r-1",
            sequence: 0,
            name: "n",
            traceType: traceType,
            status: status,
            error: error,
            startedAt: startedAt,
            endedAt: endedAt,
            latencyMs: latencyMs,
            tokensIn: tokensIn,
            tokensOut: tokensOut,
            costUsd: costUsd
        )
    }
}
