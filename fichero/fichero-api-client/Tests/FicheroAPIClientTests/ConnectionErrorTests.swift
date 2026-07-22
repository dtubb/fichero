import XCTest
import HTTPTypes
import OpenAPIRuntime
@testable import FicheroAPIClient

/// Verifies `ConnectionError.classify` names the actual cause of a transport
/// failure — Daniel's observability mandate — mapping the common URLError /
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

    func testTimedOutClassifiesAsTimedOut() {
        let classified = ConnectionError.classify(URLError(.timedOut), transport: .https)
        XCTAssertEqual(classified.kind, .timedOut)
    }

    func testURLErrorCancelledClassifiesAsCancelled() {
        let classified = ConnectionError.classify(URLError(.cancelled), transport: .https)
        XCTAssertEqual(classified.kind, .cancelled)
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

    func testUnknownErrorClassifiesAsOther() {
        struct Weird: Error {}
        let classified = ConnectionError.classify(Weird(), transport: .https)
        XCTAssertEqual(classified.kind, .other)
    }

    func testAlreadyClassifiedIsReturnedUnchanged() {
        let original = ConnectionError.classify(URLError(.timedOut), transport: .https, operationID: "op")
        let reclassified = ConnectionError.classify(original, transport: .uds(path: "/x"), operationID: "other")
        // Untouched: same kind + operation, not re-wrapped under the new transport.
        XCTAssertEqual(reclassified.kind, .timedOut)
        XCTAssertEqual(reclassified.operationID, "op")
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
