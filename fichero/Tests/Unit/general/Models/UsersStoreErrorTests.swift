@testable import Fichero
import XCTest

final class UsersStoreErrorTests: XCTestCase {
    func testErrorDescriptionReturnsBackendMessage() {
        XCTAssertEqual(
            UsersStoreError(message: "permission denied").errorDescription,
            "permission denied"
        )
    }
}
