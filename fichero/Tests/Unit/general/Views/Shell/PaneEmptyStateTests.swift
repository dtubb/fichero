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
}
