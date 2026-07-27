@testable import Fichero
import Foundation
import XCTest

final class WorkflowStreamServiceFailureTests: XCTestCase {

    private static func source() throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent("Services/WorkflowStreamService.swift")
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testNonCancellationStreamFailureDoesNotDispatchTerminalErrorToCaller() throws {
        let source = try Self.source()
        let failureRange = try XCTUnwrap(source.range(of: "private func handleStreamFailure"))
        let cancellationRange = try XCTUnwrap(source.range(of: "if !Task.isCancelled"))
        let cancelStreamRange = try XCTUnwrap(
            source.range(of: "func cancelStream()", range: failureRange.upperBound..<source.endIndex)
        )
        let failureBody = source[failureRange.lowerBound..<cancelStreamRange.lowerBound]

        XCTAssertLessThan(cancellationRange.lowerBound, failureRange.lowerBound)
        XCTAssertTrue(failureBody.contains("liveUpdatesUnavailable = true"))
        XCTAssertFalse(failureBody.contains("onEvent?"))
    }
}
