import Foundation
import OpenAPIRuntime
import XCTest
@testable import FicheroAPIClient

/// Verifies `Error.isCancellationError` — the guard the cancellation sweep uses
/// so a superseded/cancelled request is never logged as an error or surfaced as
/// a user-facing error state. The load-bearing case is the *wrapped* one: the
/// generated client throws `ClientError(underlyingError: CancellationError())`,
/// which is what produced the live "Failed to load annotations: … underlying
/// error: CancellationError()" symptom.
final class ErrorCancellationTests: XCTestCase {

    /// A stand-in for a real backend/decoding failure.
    private struct SampleFailure: Error {}

    private func makeClientError(wrapping underlying: any Error) -> ClientError {
        ClientError(
            operationID: "listAnnotations",
            operationInput: "input",
            causeDescription: "Test",
            underlyingError: underlying
        )
    }

    func testBareCancellationErrorIsCancellation() {
        XCTAssertTrue(CancellationError().isCancellationError)
    }

    func testCancelledURLErrorIsCancellation() {
        XCTAssertTrue(URLError(.cancelled).isCancellationError)
    }

    /// The reported case: a `ClientError` wrapping a `CancellationError`.
    func testClientErrorWrappingCancellationIsCancellation() {
        let wrapped = makeClientError(wrapping: CancellationError())
        XCTAssertTrue(wrapped.isCancellationError)
    }

    /// A `ClientError` wrapping a cancelled `URLError` (task torn down mid-request).
    func testClientErrorWrappingCancelledURLErrorIsCancellation() {
        let wrapped = makeClientError(wrapping: URLError(.cancelled))
        XCTAssertTrue(wrapped.isCancellationError)
    }

    func testGenuineFailureIsNotCancellation() {
        XCTAssertFalse(SampleFailure().isCancellationError)
    }

    /// A non-cancellation `URLError` (e.g. a real network failure) must NOT be
    /// treated as cancellation — otherwise real failures would be swallowed.
    func testNonCancelledURLErrorIsNotCancellation() {
        XCTAssertFalse(URLError(.timedOut).isCancellationError)
    }

    /// A `ClientError` wrapping a genuine failure stays a failure — the guard
    /// must not swallow real errors.
    func testClientErrorWrappingGenuineFailureIsNotCancellation() {
        let wrapped = makeClientError(wrapping: SampleFailure())
        XCTAssertFalse(wrapped.isCancellationError)
    }
}
