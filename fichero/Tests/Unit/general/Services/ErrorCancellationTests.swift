import FicheroAPIClient
import Foundation
import OpenAPIRuntime
import XCTest

/// Coverage for `Error.isCancellationError` — the unwrap-aware cancellation check
/// (fix/wrapped-cancellation). swift-openapi's generated client wraps a transport
/// `CancellationError` inside a `ClientError.underlyingError`, so a bare
/// `catch is CancellationError` misses a superseded request and mislogs it as a
/// failure. This asserts the helper sees through that wrapper.
final class ErrorCancellationTests: XCTestCase {

    func testBareCancellationErrorIsCancellation() {
        let error: any Error = CancellationError()
        XCTAssertTrue(error.isCancellationError)
    }

    func testNonCancellationErrorIsNotCancellation() {
        let error: any Error = URLError(.badServerResponse)
        XCTAssertFalse(error.isCancellationError)
    }

    func testURLErrorCancelledIsCancellation() {
        let error: any Error = URLError(.cancelled)
        XCTAssertTrue(error.isCancellationError)
    }

    /// The core case: the generated client wraps the transport's
    /// `CancellationError` in a `ClientError`. `ClientError`'s init is public, so
    /// we can construct the exact shape the transport produces.
    func testWrappedClientErrorUnwrapsToCancellation() {
        let wrapped = ClientError(
            operationID: "listInspectorEntitiesForDocument",
            operationInput: "input",
            causeDescription: "Transport threw an error.",
            underlyingError: CancellationError()
        )
        XCTAssertTrue(wrapped.isCancellationError)
    }

    /// A `ClientError` wrapping a URLError(.cancelled) — the URLSession transport's
    /// form of cancellation — also unwraps.
    func testWrappedClientErrorWrappingURLCancelledUnwraps() {
        let wrapped = ClientError(
            operationID: "getArtifacts",
            operationInput: "input",
            causeDescription: "Transport threw an error.",
            underlyingError: URLError(.cancelled)
        )
        XCTAssertTrue(wrapped.isCancellationError)
    }

    /// A `ClientError` wrapping a genuine failure stays a failure (not swallowed).
    func testWrappedClientErrorWrappingRealErrorIsNotCancellation() {
        let wrapped = ClientError(
            operationID: "getArtifacts",
            operationInput: "input",
            causeDescription: "Transport threw an error.",
            underlyingError: URLError(.badServerResponse)
        )
        XCTAssertFalse(wrapped.isCancellationError)
    }
}
