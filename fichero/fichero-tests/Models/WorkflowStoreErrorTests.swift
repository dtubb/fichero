@testable import Fichero
import XCTest

final class WorkflowStoreErrorTests: XCTestCase {
    func testErrorDescriptionsIdentifyFailure() {
        XCTAssertEqual(
            WorkflowStoreError.notFound("wf-1").errorDescription,
            "Not found: wf-1"
        )
        XCTAssertEqual(
            WorkflowStoreError.saveFailed("offline").errorDescription,
            "Save failed: offline"
        )
        XCTAssertEqual(
            WorkflowStoreError.executionFailed("timeout").errorDescription,
            "Execution failed: timeout"
        )
        XCTAssertEqual(
            WorkflowStoreError.templateInstallFailed("invalid").errorDescription,
            "Template install failed: invalid"
        )
    }
}
