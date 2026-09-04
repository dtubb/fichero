@testable import Fichero
import XCTest

/// What a run's cost READS as (2026-09-03).
///
/// The server now records tokens and cost per run and per step, and keeps
/// three states apart: priced, free, and unpriced. These tests hold the client
/// to the same distinction — the whole feature is worthless if the UI collapses
/// "we could not price this" into "$0.00".
final class RunCostDisplayTests: XCTestCase {

    // MARK: - RunUsage (run level)

    func testPricedRunShowsTheCost() {
        let usage = RunUsage(modelCalls: 2, totalTokens: 1200, costUsd: 0.0042, priced: true)
        XCTAssertEqual(usage.costText, "$0.0042")
        XCTAssertTrue(usage.hasUsage)
    }

    func testCostAboveACentUsesTwoDecimals() {
        let usage = RunUsage(modelCalls: 1, costUsd: 1.5, priced: true)
        XCTAssertEqual(usage.costText, "$1.50")
    }

    func testFreeRunSaysFreeNotZeroDollars() {
        // On-device: a zero we can defend.
        let usage = RunUsage(modelCalls: 3, costUsd: 0, priced: true)
        XCTAssertEqual(usage.costText, "Free")
    }

    func testUnpricedRunSaysSoInWords() {
        let usage = RunUsage(modelCalls: 1, costUsd: nil, priced: false, unpricedModels: ["mystery-1"])
        XCTAssertEqual(usage.costText, "Cost unpriced")
        XCTAssertEqual(usage.unpricedNotice, "No registry price for: mystery-1")
    }

    func testPartiallyPricedRunReadsAsAFloor() {
        let usage = RunUsage(
            modelCalls: 2,
            costUsd: 0.01,
            priced: false,
            partiallyPriced: true,
            unpricedModels: ["mystery-1"]
        )
        XCTAssertEqual(usage.costText, "≥ $0.01")
    }

    func testRunWithNoModelCallHasNothingToShow() {
        XCTAssertFalse(RunUsage().hasUsage)
    }

    func testTokenTextFlagsEstimates() {
        XCTAssertEqual(
            RunUsage(modelCalls: 1, totalTokens: 100).tokensText,
            "100 tokens · 1 call"
        )
        XCTAssertEqual(
            RunUsage(modelCalls: 2, totalTokens: 100, estimatedTokens: true).tokensText,
            "~100 tokens · 2 calls"
        )
    }

    func testUnpricedNoticeIsAbsentWhenEverythingPriced() {
        XCTAssertNil(RunUsage(modelCalls: 1, costUsd: 0.01, priced: true).unpricedNotice)
    }

    // MARK: - Decoding

    func testDecodesTheServerShape() throws {
        let json = """
        {"model_calls": 2, "input_tokens": 900, "output_tokens": 100,
         "total_tokens": 1000, "cache_read_tokens": 400, "cost_usd": 0.0031,
         "priced": true, "partially_priced": false, "estimated_tokens": false,
         "unpriced_models": []}
        """.data(using: .utf8)!
        let usage = try JSONDecoder().decode(RunUsage.self, from: json)
        XCTAssertEqual(usage.modelCalls, 2)
        XCTAssertEqual(usage.cacheReadTokens, 400)
        XCTAssertEqual(usage.costUsd, 0.0031)
        XCTAssertTrue(usage.priced)
    }

    func testDecodesANullCostWithoutTurningItIntoZero() throws {
        let json = """
        {"model_calls": 1, "cost_usd": null, "priced": false,
         "unpriced_models": ["mystery-1"]}
        """.data(using: .utf8)!
        let usage = try JSONDecoder().decode(RunUsage.self, from: json)
        XCTAssertNil(usage.costUsd)
        XCTAssertEqual(usage.costText, "Cost unpriced")
    }

    func testRunResponseWithoutUsageDecodesAsNil() throws {
        // Legacy run, recorded before cost accounting existed. Nil, not zero.
        let json = """
        {"thread_id": "t1", "workflow_id": "w1", "workflow_name": "W",
         "status": "completed"}
        """.data(using: .utf8)!
        let run = try JSONDecoder().decode(WorkflowRunResponse.self, from: json)
        XCTAssertNil(run.runUsage)
    }

    // MARK: - CostDisplay (comparison surfaces)

    func testComparisonCostFormatterKeepsUnknownDistinctFromFree() {
        XCTAssertEqual(CostDisplay.text(nil), "Unpriced")
        XCTAssertEqual(CostDisplay.text(0), "Free")
        XCTAssertEqual(CostDisplay.text(0.0042), "$0.0042")
        XCTAssertFalse(CostDisplay.isKnown(nil))
        XCTAssertTrue(CostDisplay.isKnown(0))
    }

    // MARK: - Per-step cost on the trace node

    func testTraceNodeWithNoModelCallShowsNoCost() {
        XCTAssertNil(traceNode(modelCalls: nil).costText)
        XCTAssertNil(traceNode(modelCalls: 0).costText)
    }

    func testTraceNodeShowsCostAndTokens() {
        XCTAssertEqual(
            traceNode(modelCalls: 1, totalTokens: 1204, costUsd: 0.0042, costPriced: true).costText,
            "$0.0042 · 1,204 tokens"
        )
    }

    func testTraceNodeSaysUnpricedRatherThanZero() {
        XCTAssertEqual(
            traceNode(modelCalls: 1, totalTokens: 500, costUsd: nil).costText,
            "Cost unpriced · 500 tokens"
        )
    }

    func testTraceNodeFreeStepSaysFree() {
        XCTAssertEqual(
            traceNode(modelCalls: 1, costUsd: 0, costPriced: true).costText,
            "Free"
        )
    }

    private func traceNode(
        modelCalls: Int?,
        totalTokens: Int? = nil,
        costUsd: Double? = nil,
        costPriced: Bool = false
    ) -> RunTraceNode {
        RunTraceNode(
            id: "n1",
            label: "Transcribe",
            tool: "transcribe",
            provider: "openai",
            model: "gpt-4o",
            status: .success,
            durationMs: 120,
            error: nil,
            skipReason: nil,
            modelCalls: modelCalls,
            totalTokens: totalTokens,
            costUsd: costUsd,
            costPriced: costPriced
        )
    }
}
