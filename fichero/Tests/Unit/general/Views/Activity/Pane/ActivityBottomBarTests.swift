@testable import Fichero
import Testing

/// `activity.pane.bottom-bar-like-every-pane` (#6588; spec docs/contributor_manual/specs/ui/activity-pane.md): the Filter
/// field's menu offers what the list shows, each a filter the grammar reads.
@MainActor
struct ActivityBottomBarTests {
    @Test("the filter menu's words are filters the grammar keeps: Failed, Today, Started Automatically")
    func menuFiltersParse() {
        let failed = ActivityPaneFilter("state: failed")
        let today = ActivityPaneFilter("date: today")
        let automatic = ActivityPaneFilter("started by: automatic")
        #expect(failed.tokens == [.init(key: .state, value: "failed")])
        #expect(today.tokens == [.init(key: .date, value: "today")])
        #expect(automatic.tokens == [.init(key: .startedBy, value: "automatic")])
    }

    @Test("Started Automatically keeps the kept export's row and leaves out a person's run")
    func startedAutomatically() {
        var kept = ActivityPaneFixture.row("k", .paused)
        kept.startedBy = "kept export"
        var mine = ActivityPaneFixture.row("m", .running)
        mine.startedBy = "owner"
        let filter = ActivityPaneFilter("started by: automatic")
        #expect(filter.matches(kept) && !filter.matches(mine))
    }
}
