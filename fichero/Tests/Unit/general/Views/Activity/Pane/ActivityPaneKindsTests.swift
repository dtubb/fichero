@testable import Fichero
import Foundation
import Testing

/// `activity.window.views-are-panes` and `activity.graphs.own-pane` (#6588, decisions 40-41; spec
/// docs/contributor_manual/specs/ui/activity-pane.md): a main window offers "Activity" and "Activity Graphs" panes, and
/// the graphs pane is a pane like any other: switched to from a pane's kind menu, kept in a workspace, focused for
/// Split and Close as itself.
struct ActivityPaneKindsTests {
    @Test("a main window's kind menu offers Activity and Activity Graphs")
    func offered() {
        let kinds = PaneSpec.Kind.selectableKinds
        #expect(kinds.contains(.activity) && kinds.contains(.activityGraphs))
        #expect(PaneSpec.Kind.activityGraphs.title == "Activity Graphs")
    }

    @Test("an Activity Graphs pane is kept in a workspace by its own name")
    func kept() throws {
        let data = try JSONEncoder().encode([PaneKind.activityGraphs])
        #expect(String(decoding: data, as: UTF8.self) == "[\"activityGraphs\"]")
        #expect(try JSONDecoder().decode([PaneKind].self, from: data) == [.activityGraphs])
    }

    @Test("focused, the graphs pane is its own kind for Split and Close, never the Activity table")
    func focused() {
        #expect(PaneFocus.activityGraphs.paneKind == .activityGraphs)
        #expect(PaneFocus.activity.paneKind == .activity)
        #expect(PaneFocus.activityGraphs.paneTitle == "Activity Graphs")
    }
}
