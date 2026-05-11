@testable import Fichero
import Foundation
import XCTest

/// Tests for ComparisonSummary + ComparisonHistoryResponse DTOs.
/// Locks the snake_case decode contract for /comparisons endpoints.
final class ComparisonTypesTests: XCTestCase {

    func testComparisonSummaryDecodesSnakeCase() throws {
        let json = """
        {
            "prompt": "Compare these models",
            "models_compared": ["gpt-4o", "claude-opus-4"],
            "total_cost_usd": 0.025,
            "comparison_id": "comp-1",
            "timestamp": "2026-05-11T10:00:00Z"
        }
        """.data(using: .utf8)!
        let summary = try JSONDecoder().decode(ComparisonSummary.self, from: json)
        XCTAssertEqual(summary.id, "comp-1")  // id derived from comparisonId
        XCTAssertEqual(summary.modelsCompared, ["gpt-4o", "claude-opus-4"])
        XCTAssertEqual(summary.totalCostUsd, 0.025)
        XCTAssertEqual(summary.comparisonId, "comp-1")
    }

    func testComparisonHistoryResponseDecodes() throws {
        let json = """
        {
            "history": [
                {
                    "prompt": "p",
                    "models_compared": [],
                    "total_cost_usd": 0,
                    "comparison_id": "c",
                    "timestamp": "t"
                }
            ]
        }
        """.data(using: .utf8)!
        let resp = try JSONDecoder().decode(ComparisonHistoryResponse.self, from: json)
        XCTAssertEqual(resp.history.count, 1)
        XCTAssertEqual(resp.history.first?.comparisonId, "c")
    }

    func testComparisonSummaryHashable() {
        // Sidebar list uses Hashable to dedupe selection — two instances
        // with identical fields must hash equal.
        let a = ComparisonSummary(
            prompt: "p", modelsCompared: ["m"],
            totalCostUsd: 0.1, comparisonId: "c", timestamp: "t"
        )
        let b = ComparisonSummary(
            prompt: "p", modelsCompared: ["m"],
            totalCostUsd: 0.1, comparisonId: "c", timestamp: "t"
        )
        XCTAssertEqual(a, b)
        XCTAssertEqual(a.hashValue, b.hashValue)
    }
}
