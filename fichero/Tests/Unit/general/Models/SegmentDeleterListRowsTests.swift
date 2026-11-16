@testable import Fichero
import Testing

// Spec: source.editor.order-list-edits-like-finder (#6476), source/segment-editor-crud.md.
//
// Delete with several rows of the Order list selected deleted nothing: the list asked the shared
// selection (empty when it lags behind the list) and its one-row `selection` (nil for several).
// The list's own picks are the rows now (`SegmentDeleter.listRows`), for the Delete key, the row
// menu and the menu bar alike.

@Suite("Order list: Delete takes the list's own picks (#6476)")
struct SegmentDeleterListRowsTests {

    private let order = ["l1", "l2", "l3", "l4"]

    @Test("Delete on several picked rows takes them all, in the list's order, whatever the shared selection holds")
    func severalPicksAreTheRows() {
        #expect(SegmentDeleter.listRows(picked: ["l4", "l2"], order: order, held: []) == ["l2", "l4"])
        #expect(SegmentDeleter.listRows(picked: ["l4", "l2"], order: order, held: ["l1"]) == ["l2", "l4"])
    }

    @Test("Delete on one picked row keeps the one-row rule: the held selection only when it holds the row")
    func onePickKeepsTheRowRule() {
        #expect(SegmentDeleter.listRows(picked: ["l2"], order: order, held: ["l2", "l3"]) == ["l2", "l3"])
        #expect(SegmentDeleter.listRows(picked: ["l2"], order: order, held: ["l3"]) == ["l2"])
        #expect(SegmentDeleter.listRows(picked: [], order: order, held: ["l3"]) == ["l3"])
    }
}
