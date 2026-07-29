@testable import Fichero
import XCTest

final class APIErrorTests: XCTestCase {
    func testErrorDescriptionsClassifyEachFailure() {
        XCTAssertEqual(APIError.invalidResponse.errorDescription, "Invalid response from server")
        XCTAssertEqual(APIError.badRequest("missing name").errorDescription, "Bad request: missing name")
        XCTAssertEqual(APIError.notFound("document").errorDescription, "Not found: document")
        XCTAssertEqual(APIError.serverError("offline").errorDescription, "Server error: offline")
        XCTAssertEqual(APIError.httpError(statusCode: 503, message: "busy").errorDescription, "HTTP 503: busy")
        XCTAssertTrue(APIError.connectionFailed.errorDescription?.contains("fichero serve") == true)
    }
}
