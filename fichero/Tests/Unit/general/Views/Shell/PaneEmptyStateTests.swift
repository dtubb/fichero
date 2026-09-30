@testable import Fichero
import Foundation
import Testing

/// #5273: an empty pane says which pane it is and what would fill it. Four panes showing the same
/// grey "No selection" read as a row of identical labels.
struct PaneEmptyStateTests {

    @Test("every empty pane has a title and a hint, and none says 'No selection'")
    func copyNamesThePane() {
        for pane in PaneEmptyState.allCases {
            #expect(!pane.title.isEmpty && !pane.hint.isEmpty, "\(pane)")
            #expect(pane.title.lowercased() != "no selection", "\(pane)")
        }
        #expect(PaneEmptyState.reader.hint.contains("Library"))
    }

    @Test("no pane draws a bare 'No selection' any more")
    func noBareNoSelectionText() throws {
        for path in [
            "Views/Reader/Page/ReadingPaneView+Tabs.swift",
            "Views/Inspector/Document/DocumentInspector.swift",
            "Views/Shell/ContentView/ContentView+KnowledgeSurface.swift",
            "Views/Preview/EditorView.swift",
        ] {
            let source = try String(contentsOf: AppSource.root().appendingPathComponent(path), encoding: .utf8)
            #expect(!source.contains("Text(\"No selection\")"), "\(path)")
            #expect(source.contains("PaneEmptyState."), "\(path)")
        }
    }
}
