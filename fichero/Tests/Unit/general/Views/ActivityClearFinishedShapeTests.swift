@testable import Fichero
import XCTest

/// #5016 (`activity.window.clear-finished`): one way to empty the Activity list of everything that has ended.
/// What breaks without it: only "Clear Failed" existed, so completed runs piled up with no bulk removal.
final class ActivityClearFinishedShapeTests: XCTestCase {
    func testTheToolbarOffersClearFinishedBehindAConfirmation() throws {
        let window = try AppSource.code("Views/Activity/Window/ActivityMonitorWindow.swift")
        // The button sits under the DONE TODAY heading (ActivityGroupsView) and asks the window to confirm.
        let groups = try AppSource.code("Views/Activity/Window/ActivityGroupsView.swift")
        XCTAssertTrue(groups.contains("Button(\"Clear Finished…\", role: .destructive, action: clearFinished)"))
        XCTAssertTrue(window.contains("clearFinished: { confirmingClearFinished = true }"))
        XCTAssertTrue(window.contains(".confirmationDialog(\"Remove every finished run?\""))
    }

    func testItDeletesEndedStatusesOnlyNeverRunningOnes() throws {
        let window = try AppSource.code("Views/Activity/Window/ActivityMonitorWindow.swift")
        XCTAssertTrue(window.contains("deleteRuns(statuses: ActivityRunStatus.finishedEngineNames)"))
        XCTAssertTrue(window.contains("ActivityRunStatus.finished.contains($0.status)"))
        XCTAssertFalse(window.contains("statuses: [\"running\""))
    }

    func testTheEnginesNamesAreTheEndedStatuses() {
        XCTAssertEqual(Set(ActivityRunStatus.finishedEngineNames), ["completed", "failed", "cancelled"])
    }
}
