@testable import Fichero
import Testing

/// The Activity pane's verbs (spec docs/contributor_manual/specs/ui/activity-pane.md). The toolbar verbs bar these tests
/// once covered was removed 2026-11-15: the run controls (`ActivityRunControlsTests`) replaced it.
@MainActor
struct ActivityToolbarVerbsTests {
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
