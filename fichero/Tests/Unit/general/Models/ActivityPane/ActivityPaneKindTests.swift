//
//  ActivityPaneKindTests.swift — `activity.pane.is-a-pane-kind` (#6441): Activity is a pane kind, offered by every
//  pane head's kind switcher, round-tripping through a saved workspace, scoped by its project; the sidebar shows it.
//

@testable import Fichero
import Foundation
import Testing

struct ActivityPaneKindTests {
    @Test("the kind switcher lists Activity, and the model and view kinds map to each other")
    func inTheSwitcher() {
        #expect(PaneSpec.Kind.selectableKinds.contains(.activity))
        #expect(PaneKind.allCases.contains(.activity))
        #expect(PaneSpec.Kind.activity.title == "Activity")
        #expect(PaneFocus.activity.paneKind == .activity)
        #expect(UIPane.activity.paneKind == .activity)
    }

    @Test("a Reader pane switched to Activity keeps its id and scope, and a saved workspace restores the Activity leaf")
    func roundTrip() throws {
        let library = UUID()
        let reader = PaneNode.leaf(.reading, scope: PaneScope(libraryId: library))
        let switched = reader.changingKind(reader.id, to: .activity)
        guard case let .leaf(id, kind, scope, _) = switched else { Issue.record("not a leaf"); return }
        #expect(id == reader.id && kind == .activity && scope.libraryId == library)
        let saved = try JSONEncoder().encode(PaneNode.split(.horizontal, [switched, .leaf(.preview)]))
        let restored = try JSONDecoder().decode(PaneNode.self, from: saved)
        #expect(restored.kinds.contains(.activity))
    }

    @Test("the pane renders scoped to the window's project, its selection the window's; the sidebar shows the same pane")
    func mounted() throws {
        let specs = try AppSource.code("Views/Shell/ContentView/Layout/ContentView+PaneSpecs.swift")
        #expect(specs.contains("ActivityPaneView(libraryId: windowState.libraryId, showsHead: true"))
        #expect(specs.contains("onSelect: { windowState.activityPick = $0 }"))
        let navigation = try AppSource.code("Views/Shell/ContentView/ContentView+Navigation.swift")
        #expect(navigation.contains("ActivityPaneView(libraryId: windowState.libraryId, showsHead: false"))
        #expect(!navigation.contains("ActivityBrowserView"), "the sidebar mode's own job list is gone")
    }
}
