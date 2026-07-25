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

    func testNonCancellationStreamFailureDispatchesTerminalErrorToCaller() throws {
        let source = try Self.source()
        let failureRange = try XCTUnwrap(source.range(of: "private func handleStreamFailure"))
        let cancellationRange = try XCTUnwrap(source.range(of: "if !Task.isCancelled"))

        XCTAssertLessThan(cancellationRange.lowerBound, failureRange.lowerBound)
        XCTAssertNotNil(
            source.range(
                of: "onEvent?(.error(threadId: threadId, error: message))",
                range: failureRange.lowerBound..<source.endIndex
            )
        )
    }
}
