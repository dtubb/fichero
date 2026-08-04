@testable import Fichero
import Foundation
import XCTest

final class WorkflowStreamServiceFailureTests: XCTestCase {

    private static func source() throws -> String {
        let url = try AppSource.root()
            .appendingPathComponent("Services/WorkflowStreamService.swift")
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testNonCancellationStreamFailureDoesNotDispatchTerminalErrorToCaller() throws {
        let source = try Self.source()
        let failureRange = try XCTUnwrap(source.range(of: "private func handleStreamFailure"))
        let cancellationRange = try XCTUnwrap(source.range(of: "if !Task.isCancelled"))
        // Anchor matches the signature loosely — the workflows lane made
        // cancelStream per-thread (cancelStream(threadId:)) without changing
        // the failure-path behavior this guard protects.
        let cancelStreamRange = try XCTUnwrap(
            source.range(of: "func cancelStream(", range: failureRange.upperBound..<source.endIndex)
        )
        let failureBody = source[failureRange.lowerBound..<cancelStreamRange.lowerBound]

        XCTAssertLessThan(cancellationRange.lowerBound, failureRange.lowerBound)
        XCTAssertTrue(failureBody.contains("liveUpdatesUnavailable = true"))
        XCTAssertFalse(failureBody.contains("onEvent?"))
    }

    func testStartingAnotherRunDoesNotCancelExistingStream() throws {
        let source = try Self.source()
        let executeRange = try XCTUnwrap(source.range(of: "func execute("))
        let subscribeRange = try XCTUnwrap(
            source.range(of: "func subscribe(", range: executeRange.upperBound..<source.endIndex)
        )
        let executeBody = source[executeRange.lowerBound..<subscribeRange.lowerBound]

        XCTAssertTrue(source.contains("streamTasks: [String: Task<Void, Never>]"))
        XCTAssertFalse(executeBody.contains(".cancel()"))
        // Two pins, not one substring: 4cf3582c7 (#4457) rewrapped the call
        // across lines when it gained onStreamEnd, and a single-line literal
        // stopped matching a call whose shape is unchanged.
        XCTAssertTrue(executeBody.contains("startStream("))
        XCTAssertTrue(executeBody.contains("threadId: acceptedResponse.threadId"))
        XCTAssertTrue(source.contains("cancelStream(threadId: threadId)"))
    }
}
