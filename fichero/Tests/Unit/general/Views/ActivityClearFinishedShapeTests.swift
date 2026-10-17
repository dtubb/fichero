@testable import Fichero
import XCTest

/// #5016 (`activity.window.clear-finished`): one way to empty the Activity list of everything that has ended.
/// What breaks without it: only "Clear Failed" existed, so completed runs piled up with no bulk removal.
final class ActivityClearFinishedShapeTests: XCTestCase {
    func testTheToolbarOffersClearFinishedBehindAConfirmation() throws {
        let window = try AppSource.code("Views/Activity/Window/ActivityMonitorWindow.swift")
        XCTAssertTrue(window.contains("Button(\"Clear Finished…\", role: .destructive) { confirmingClearFinished = true }"))
        XCTAssertTrue(window.contains(".confirmationDialog(\"Remove every finished run?\""))
    }

    func testItDeletesEndedStatusesOnlyNeverRunningOnes() throws {
        let window = try AppSource.code("Views/Activity/Window/ActivityMonitorWindow.swift")
        XCTAssertTrue(window.contains("deleteRuns(statuses: [\"completed\", \"failed\", \"cancelled\"])"))
        XCTAssertFalse(window.contains("statuses: [\"running\""))
    }
}
