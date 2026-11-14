//
//  ActivityWindowIsAPaneTests.swift — `activity.window.is-the-pane-plus-inspector`, `activity.one-window`,
//  `activity.pane.inspector-shows-the-selected-row` and `activity.pane.commands-through-the-table` (#6441): one window,
//  the pane plus the Inspector; the details mounted once; the verbs in Project › Activity from one definition.
//

@testable import Fichero
import Testing

@MainActor
struct ActivityWindowIsAPaneTests {
    @Test("the main window's Inspector shows the Activity section while the Activity pane holds the focus")
    func mainInspector() {
        #expect(ContentView.inspectsActivity(focus: .activity, mode: .batches))
        #expect(ContentView.inspectsActivity(focus: nil, mode: .activity(nil)), "the sidebar's Activity")
        #expect(!ContentView.inspectsActivity(focus: .preview, mode: .batches), "another pane: the document's sections")
        #expect(!ContentView.inspectsActivity(focus: nil, mode: .library(nil)))
    }

    @Test("Show in Activity selects its row in the one window")
    func showInActivity() {
        let state = ActivityWindowSelectionState()
        state.select(ActivitySelection(jobId: "run-1", libraryId: nil))
        #expect(state.reveal?.jobId == "run-1")
    }

    @Test("Project › Activity lists the one verb list once, enabled by the pane's selection")
    func commands() {
        #expect(FocusedActivityVerbButtons.verbs == [.pause, .resume, .retry, .archive, .putBack, .delete])
        #expect(Set(FocusedActivityVerbButtons.verbs).count == FocusedActivityVerbButtons.verbs.count)
    }
}
