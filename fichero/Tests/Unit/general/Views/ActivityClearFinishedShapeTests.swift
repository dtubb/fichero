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
        // #6599: the ended jobs and runs are archived as ONE undoable step (job.archive by states, workflow_run.archive).
        XCTAssertTrue(actions.contains("archive(states: [\"done\", \"failed\", \"cancelled\"], runStatuses: ActivityRunStatus.finished)"))
        XCTAssertTrue(actions.contains("store.archiveAsOneStep(states: states, threadIds: ended"))
        XCTAssertFalse(actions.contains("statuses: [\"running\""))
    }

    func testTheEnginesNamesAreTheEndedStatuses() {
        XCTAssertEqual(Set(ActivityRunStatus.finishedEngineNames), ["completed", "failed", "cancelled"])
    }
}
