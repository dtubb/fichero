@testable import Fichero
import XCTest

final class ErrorResponseTests: XCTestCase {
    func testDecodesBackendDetail() throws {
        let response = try JSONDecoder().decode(
            ErrorResponse.self,
            from: Data(#"{"detail":"invalid request"}"#.utf8)
        )

        XCTAssertEqual(response.detail, "invalid request")
    }
}
