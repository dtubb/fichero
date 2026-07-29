@testable import Fichero
import XCTest

final class WorkflowExecutionErrorTests: XCTestCase {
    func testErrorDescriptionsPreserveServerContext() {
        XCTAssertEqual(
            WorkflowExecutionError.invalidResponse.errorDescription,
            "Invalid response from server"
        )
        XCTAssertEqual(
            WorkflowExecutionError.serverError(422, "invalid workflow").errorDescription,
            "Server error (422): invalid workflow"
        )
    }
}
