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
        let reader = PaneNode.leaf(.reading, scope: PaneScope(libraryId: library.uuidString))
        let switched = reader.changingKind(reader.id, to: .activity)
        guard case let .leaf(id, kind, scope, _) = switched else { Issue.record("not a leaf"); return }
        #expect(id == reader.id && kind == .activity && scope.libraryId == library.uuidString)
        let saved = try JSONEncoder().encode(PaneNode.split(.horizontal, [switched, .leaf(.preview)]))
        let restored = try JSONDecoder().decode(PaneNode.self, from: saved)
        #expect(restored.kinds.contains(.activity))
    }
}
