@testable import Fichero
import Testing

/// `activity.pane.row-controls` (#6588, decision 31): the selected or hovered row shows its own Play/Pause and Stop, by its
/// state, through the one verb list; nothing it does not allow, nothing its worded button already offers.
struct ActivityRowControlsTests {
    @Test("a running row offers Pause and Stop; a paused one Stop beside its Continue button; a done one nothing")
    func byState() {
        let running = ActivityPaneFixture.row("r", .running)
        #expect(running.paneButton == .verb(.pause))
        #expect(running.rowControls == [.stop], "Pause is its worded button already")
        let waiting = ActivityPaneFixture.row("w", .waiting)
        #expect(Set(waiting.rowControls + [waiting.paneButton].compactMap { if case .verb(let verb) = $0 { verb } else { nil } })
            .isSuperset(of: [.pause, .stop]))
        let paused = ActivityPaneFixture.row("p", .paused)
        #expect(paused.rowControls.contains(.stop) && !paused.rowControls.contains(.pause))
        #expect(ActivityPaneFixture.row("d", .done).rowControls.isEmpty)
    }

    @Test("a row with no job takes no control")
    func noJob() {
        #expect(ActivityPaneFixture.row("x", .running, jobId: nil).rowControls.isEmpty)
    }
}
