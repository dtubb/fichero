@testable import Fichero
import Testing

/// `activity.window.sidebar` (#6588, decision 32): the Activity window's sidebar replaces the toolbar's tabs; each item is a
/// grouping and a column set over the same rows; Archived lists the archived rows only; Runs counts the rows needing you.
struct ActivityWindowSidebarTests {
    @Test("the sidebar lists the work, then the resources, then Archived; every tab is in it once")
    func items() {
        let listed = ActivityPane.Tab.sidebarWork + ActivityPane.Tab.sidebarResources + [.archived]
        #expect(listed.map(\.title) == ["Runs", "Files", "Recipes", "Cost", "Where", "Archived"])
        #expect(Set(listed) == Set(ActivityPane.Tab.allCases))
    }

    @Test("Archived lists by run with when it started, and its columns are its own")
    func archived() {
        #expect(ActivityPane.Tab.archived.grouping == .run)
        #expect(ActivityPane.Tab.archived.columns.contains(.started))
    }

    @Test("the Runs badge counts what needs you: failed, partial and paused for a cause, never paused by you or archived")
    func badge() {
        let failed = ActivityPaneFixture.row("f", .failed)
        let partial = ActivityPaneFixture.row("p", .partial)
        var byYou = ActivityPaneFixture.row("y", .paused)
        byYou.reason = "Paused by you"
        var archived = ActivityPaneFixture.row("a", .failed)
        archived.isArchived = true
        let running = ActivityPaneFixture.row("r", .running)
        #expect(ActivityPane.needsYouCount([failed, partial, byYou, archived, running]) == 2)
    }
}
