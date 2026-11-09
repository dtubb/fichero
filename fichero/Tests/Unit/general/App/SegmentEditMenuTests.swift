@testable import Fichero
import Foundation
import Testing

/// #6413 (segment-editor-crud Step 1.2, menus Step 2.3, part a): the segment verbs live in Edit › Segments ▸, Delete takes
/// ⌘⌫ when the Preview holds segments, and Select All Segments is one of the submenu's items. The menus cannot be mounted in
/// a unit target; what they say and act on can.
@MainActor
@Suite("Edit › Segments ▸ (#6413)")
struct SegmentEditMenuTests {
    private func target(selected: Int, onDelete: @escaping () -> Void = {}, onSelectAll: @escaping () -> Void = {}) -> SegmentMenuTarget {
        SegmentMenuTarget(
            isEditing: false, selectionCount: selected, toggleEditing: {}, canSelectAll: true,
            selectAll: onSelectAll, delete: onDelete, join: {}, apply: { _ in }
        )
    }

    @Test("Delete says how many segments it takes, and needs a selection but no mode")
    func deleteNeedsASelectionNotAMode() {
        #expect(SegmentMenuContent.deleteTitle(1) == "Delete Segment")
        #expect(SegmentMenuContent.deleteTitle(3) == "Delete 3 Segments")
        #expect(!SegmentMenuContent.canDelete(selected: 0))
        #expect(SegmentMenuContent.canDelete(selected: 1))
    }

    @Test("⌘⌫ deletes segments only when the Preview holds the focus and has segments selected")
    func commandDeleteRoute() {
        #expect(SegmentDeleteRoute.takesDelete(focusedPane: .preview, selectedSegments: 2))
        #expect(!SegmentDeleteRoute.takesDelete(focusedPane: .preview, selectedSegments: 0))
        #expect(!SegmentDeleteRoute.takesDelete(focusedPane: .sidebar, selectedSegments: 2))
        #expect(!SegmentDeleteRoute.takesDelete(focusedPane: nil, selectedSegments: 2))
    }

    @Test("the submenu's Delete and Select All Segments call the Preview's own verbs")
    func itemsReachTheSameCalls() {
        var deleted = 0
        var selectedAll = 0
        let menu = target(selected: 2, onDelete: { deleted += 1 }, onSelectAll: { selectedAll += 1 })
        menu.delete()
        menu.selectAll()
        #expect(deleted == 1 && selectedAll == 1)
    }
}
