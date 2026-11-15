@testable import Fichero
import Testing

/// `activity.window.toolbar-verbs` (#6588, decision 24; spec docs/contributor_manual/specs/ui/activity-pane.md): Pause,
/// Continue and Stop are toolbar buttons enabled by the Mail rule over the selection, through the one verb list the pane
/// publishes; a main window shows them only while its Activity pane holds the focus.
@MainActor
struct ActivityToolbarVerbsTests {
    private func target(_ rows: [ActivityMonitorRow]) -> ActivityVerbTarget {
        ActivityVerbTarget(enabled: ActivityVerbTarget.enabledVerbs(for: rows), selectionIds: Set(rows.map(\.id)), perform: { _ in })
    }

    @Test("a running and a paused row selected enable all three; a done row alone enables none")
    func mailRule() {
        let running = ActivityPaneFixture.row("r", .running)
        let paused = ActivityPaneFixture.row("p", .paused)
        #expect(ActivityToolbarVerbButtons.enabled(target([running, paused])) == [.pause, .resume, .stop])
        #expect(ActivityToolbarVerbButtons.enabled(target([ActivityPaneFixture.row("d", .done)])).isEmpty)
    }

    @Test("with no Activity pane in focus nothing is enabled, and the main window draws nothing")
    func noPaneNoVerbs() {
        #expect(ActivityToolbarVerbButtons.enabled(nil).isEmpty)
        #expect(ActivityToolbarVerbButtons(hidesWithoutAPane: true).hidesWithoutAPane)
    }

    @Test("the toolbar's verbs are the one list's Pause, Continue and Stop, in that order, with their words")
    func oneList() {
        #expect(ActivityToolbarVerbButtons.verbs.map(\.title) == ["Pause", "Continue", "Stop"])
    }
}
