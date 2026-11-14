@testable import Fichero
import XCTest

/// #5016 (`activity.window.clear-finished`, renamed Archive Finished… by `activity.pane.archive-old-runs`): one way to empty
/// the Activity list of everything that has ended. What breaks without it: completed runs piled up with no bulk removal.
final class ActivityClearFinishedShapeTests: XCTestCase {
    func testThePaneOffersArchiveFinishedBehindAConfirmation() throws {
        let pane = try AppSource.code("Views/Activity/Pane/ActivityPaneView.swift")
        XCTAssertTrue(pane.contains("Button(\"Archive Finished…\") { confirmingArchiveFinished = true }"))
        XCTAssertTrue(pane.contains(".confirmationDialog(\"Archive every finished run?\""))
    }

    func testItArchivesEndedStatusesOnlyNeverRunningOnes() throws {
        let actions = try AppSource.code("Views/Activity/Pane/ActivityPaneView+Actions.swift")
        XCTAssertTrue(actions.contains("deleteRuns(statuses: ActivityRunStatus.finishedEngineNames)"))
        XCTAssertTrue(actions.contains("archiveJobs(ids: [], states: [\"done\", \"failed\", \"cancelled\"])"))
        XCTAssertFalse(actions.contains("statuses: [\"running\""))
    }

    func testTheEnginesNamesAreTheEndedStatuses() {
        XCTAssertEqual(Set(ActivityRunStatus.finishedEngineNames), ["completed", "failed", "cancelled"])
    }
}
