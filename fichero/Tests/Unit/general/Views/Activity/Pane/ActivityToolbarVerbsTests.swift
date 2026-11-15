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
        #expect(ActivityToolbarVerbsBar.enabled(target([running, paused])) == [.pause, .resume, .stop])
        #expect(ActivityToolbarVerbsBar.enabled(target([ActivityPaneFixture.row("d", .done)])).isEmpty)
    }

    @Test("with no Activity pane in focus nothing is enabled, and the main window draws nothing")
    func noPaneNoVerbs() {
        #expect(ActivityToolbarVerbsBar.enabled(nil).isEmpty)
        #expect(ActivityToolbarVerbsBar(hidesWithoutAPane: true).hidesWithoutAPane)
    }

    @Test("the toolbar's verbs are the one list's Pause, Continue and Stop, in that order, with their words")
    func oneList() {
        #expect(ActivityToolbarVerbsBar.verbs.map(\.title) == ["Pause", "Continue", "Stop"])
    }

    /// `activity.pane.verbs-one-word-each` (#6599): Retry is the one verb for running a failed row again; a failed run's
    /// Retry reads the pages it did not do, so Project › Activity and the row's context menu carry no Read Again beside it.
    @Test("a failed or partial run is retried by Retry, the one verb Project › Activity lists for it")
    func retryIsTheOneVerb() {
        for phase: ActivityMonitorRow.Phase in [.failed, .partial] {
            let run = ActivityPaneFixture.row("run", phase, kind: .run)
            #expect(ActivityVerbTarget.enabledVerbs(for: [run]).contains(.retry))
        }
        #expect(FocusedActivityVerbButtons.verbs.contains(.retry))
        #expect(!ActivityPaneVerb.allCases.map(\.title).contains { $0.localizedCaseInsensitiveContains("read") })
    }
}
