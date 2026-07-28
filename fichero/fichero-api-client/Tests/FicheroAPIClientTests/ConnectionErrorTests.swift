import XCTest
import HTTPTypes
import OpenAPIRuntime
@testable import FicheroAPIClient

/// Verifies `ConnectionError.classify` names the actual cause of a transport
/// failure — the user's observability mandate — mapping the common URLError /
/// ClientError / cancellation shapes to a small typed `Kind`, and that
/// `description` reads as a one-line summary carrying the transport + operation.
final class ConnectionErrorTests: XCTestCase {

    /// Build a `ClientError` the way the runtime does, wrapping an arbitrary
    /// underlying error under a known operation id + request path.
    private func makeClientError(
        underlying: any Error,
        operationID: String = "inspector_get",
        path: String = "/api/documents/abc/inspector"
    ) -> ClientError {
        ClientError(
            operationID: operationID,
            operationInput: "input",
            request: HTTPRequest(method: .get, scheme: nil, authority: nil, path: path),
            causeDescription: "transport failed",
            underlyingError: underlying
        )
    }

    // MARK: - Kind mapping

    func testClientErrorWrappingCancellationClassifiesAsCancelled() {
        let clientError = makeClientError(underlying: CancellationError())
        let classified = ConnectionError.classify(clientError, transport: .uds(path: "/tmp/f.sock"))
        XCTAssertEqual(classified.kind, .cancelled)
        // Context is lifted off the ClientError.
        XCTAssertEqual(classified.operationID, "inspector_get")
        XCTAssertEqual(classified.endpointPath, "/api/documents/abc/inspector")
    }

    func testCannotConnectToHostClassifiesAsConnectionRefused() {
        let classified = ConnectionError.classify(
            URLError(.cannotConnectToHost),
            transport: .https,
            operationID: "list_documents"
        )
        XCTAssertEqual(classified.kind, .connectionRefused)
    }

    func testNetworkConnectionLostClassifiesAsConnectionRefused() {
        let classified = ConnectionError.classify(URLError(.networkConnectionLost), transport: .https)
        XCTAssertEqual(classified.kind, .connectionRefused)
    }

    func testSecureConnectionFailedClassifiesAsTLSFailure() {
        let classified = ConnectionError.classify(URLError(.secureConnectionFailed), transport: .https)
        XCTAssertEqual(classified.kind, .tlsFailure)
    }

    func testServerCertificateUntrustedClassifiesAsTLSFailure() {
        let classified = ConnectionError.classify(URLError(.serverCertificateUntrusted), transport: .https)
        XCTAssertEqual(classified.kind, .tlsFailure)
    }

    func testTimedOutClassifiesAsTimedOutAndRetryable() {
        let classified = ConnectionError.classify(URLError(.timedOut), transport: .https)
        XCTAssertEqual(classified.kind, .timedOut)
        XCTAssertEqual(classified.failureClass, .retryable)
        XCTAssertTrue(classified.isRetryable)
    }

    func testURLErrorCancelledClassifiesAsCancelledAndNotRetryable() {
        let classified = ConnectionError.classify(URLError(.cancelled), transport: .https)
        XCTAssertEqual(classified.kind, .cancelled)
        XCTAssertEqual(classified.failureClass, .cancelled)
        XCTAssertFalse(classified.isRetryable)
    }

    func testBareCancellationErrorClassifiesAsCancelled() {
        let classified = ConnectionError.classify(CancellationError(), transport: .https)
        XCTAssertEqual(classified.kind, .cancelled)
    }

    func testStreamingErrorClassifiesAsTransportUnavailable() {
        let classified = ConnectionError.classify(
            FicheroStreamingError.invalidRequestTarget,
            transport: .uds(path: "/tmp/f.sock")
        )
        XCTAssertEqual(classified.kind, .transportUnavailable)
    }

    func testDecodingErrorClassifiesAsMalformedAndFatal() {
        let classified = ConnectionError.classify(
            DecodingError.dataCorrupted(.init(codingPath: [], debugDescription: "bad JSON")),
            transport: .https
        )
        XCTAssertEqual(classified.kind, .malformedResponse)
        XCTAssertEqual(classified.failureClass, .fatal)
        XCTAssertFalse(classified.isRetryable)
    }

    func testUnknownErrorClassifiesAsOther() {
        struct Weird: Error {}
        let classified = ConnectionError.classify(Weird(), transport: .https)
        XCTAssertEqual(classified.kind, .other)
        XCTAssertEqual(classified.failureClass, .fatal)
    }

    func testAlreadyClassifiedIsReturnedUnchanged() {
        let original = ConnectionError.classify(URLError(.timedOut), transport: .https, operationID: "op")
        let reclassified = ConnectionError.classify(original, transport: .uds(path: "/x"), operationID: "other")
        // Untouched: same kind + operation, not re-wrapped under the new transport.
        XCTAssertEqual(reclassified.kind, .timedOut)
        XCTAssertEqual(reclassified.operationID, "op")
    }

    func testHTTP5xxClassifiesAsServerErrorAndRetryable() throws {
        let classified = try XCTUnwrap(ConnectionError.httpStatus(
            503,
            transport: .https,
            operationID: "list_documents",
            endpointPath: "/api/documents"
        ))
        XCTAssertEqual(classified.kind, .serverError)
        XCTAssertEqual(classified.failureClass, .retryable)
        XCTAssertTrue(classified.isRetryable)
        XCTAssertEqual((classified.underlying as? ConnectionError.HTTPStatusFailure)?.statusCode, 503)
    }

    func testHTTPAuthNotFoundAndMalformedAreFatal() throws {
        let unauthorized = try XCTUnwrap(ConnectionError.httpStatus(401, transport: .https))
        XCTAssertEqual(unauthorized.kind, .unauthorized)
        XCTAssertEqual(unauthorized.failureClass, .fatal)

        let forbidden = try XCTUnwrap(ConnectionError.httpStatus(403, transport: .https))
        XCTAssertEqual(forbidden.kind, .unauthorized)
        XCTAssertEqual(forbidden.failureClass, .fatal)

        let notFound = try XCTUnwrap(ConnectionError.httpStatus(404, transport: .https))
        XCTAssertEqual(notFound.kind, .notFound)
        XCTAssertEqual(notFound.failureClass, .fatal)

        let badRequest = try XCTUnwrap(ConnectionError.httpStatus(400, transport: .https))
        XCTAssertEqual(badRequest.kind, .malformedResponse)
        XCTAssertEqual(badRequest.failureClass, .fatal)
    }

    func testHTTPSuccessAndRedirectDoNotCreateConnectionError() {
        XCTAssertNil(ConnectionError.httpStatus(200, transport: .https))
        XCTAssertNil(ConnectionError.httpStatus(302, transport: .https))
    }

    // MARK: - description

    func testDescriptionIncludesTransportAndOperation() {
        let clientError = makeClientError(underlying: URLError(.cannotConnectToHost))
        let classified = ConnectionError.classify(clientError, transport: .uds(path: "/tmp/f.sock"))
        let description = classified.description
        XCTAssertTrue(description.contains("UDS transport"), "should name the transport: \(description)")
        XCTAssertTrue(description.contains("connection refused"), "should name the cause: \(description)")
        XCTAssertTrue(description.contains("inspector_get"), "should name the operation: \(description)")
        XCTAssertTrue(
            description.contains("/api/documents/abc/inspector"),
            "should name the endpoint path: \(description)"
        )
    }

    func testHTTPSDescriptionLabelsTransport() {
        let classified = ConnectionError.classify(
            URLError(.secureConnectionFailed),
            transport: .https,
            operationID: "list_workflows"
        )
        XCTAssertTrue(classified.description.hasPrefix("HTTPS transport:"), classified.description)
        XCTAssertTrue(classified.description.contains("list_workflows"), classified.description)
    }
}
