@testable import Fichero
import Foundation
import Testing

/// Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.order-by-clicking`. In Order, clicks number
/// segments 1, 2, 3 …; a numbered one clicked again loses its number; ⇧ on the first click continues after the selected
/// segment; leaving the tool sends the clicks ONCE as `reading_order.sequence` in the pass's `as-written` order. What
/// breaks without these: a call per click (an undo per click), or a sequence sent into the wrong order.
@MainActor
@Suite(.tags(.paleography))
struct OrderToolTests {
    @Test("clicks number segments in turn; a second click takes the number away; ⇧ on the first continues after")
    func clicks() throws {
        let window = WindowState(libraryId: UUID())
        window.orderArmed = true
        window.clickInOrder("c", after: "a")
        window.clickInOrder("b", after: nil)
        window.clickInOrder("d", after: nil)
        window.clickInOrder("b", after: nil)
        #expect(window.orderClicks == ["c", "d"])
        #expect(window.orderAfter == "a", "⇧ on the first click continues after the selection")
        #expect(window.takeOrderClicks() == nil, "nothing is sent while the tool is chosen")

        window.orderArmed = false
        let taken = try #require(window.takeOrderClicks())
        #expect(taken.segmentIds == ["c", "d"])
        #expect(taken.after == "a")
        #expect(window.takeOrderClicks() == nil, "sent once")
    }

    @Test("another tool leaves Order")
    func anotherToolLeaves() {
        let window = WindowState(libraryId: UUID())
        window.activeMarkupTool = .select
        window.orderArmed = true
        window.activeMarkupTool = .drawRegion
        #expect(!window.orderArmed)
    }

    @Test("the clicks are one reading_order.sequence in the pass's as-written order")
    func oneCall() throws {
        let orders = [
            ReadingOrderSummary(id: "named", name: "by hand", kind: "named", passId: "p"),
            ReadingOrderSummary(id: "aw-other", name: "as-written", kind: "as_written", passId: "q"),
            ReadingOrderSummary(id: "aw", name: "as-written", kind: "as_written", passId: "p")
        ]
        let call = try SegmentEdit.sequence(["c", "d"], after: "a", passId: "p", orders: orders).get()
        let data = try JSONEncoder().encode(call.params)
        let params = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(call.action == "reading_order.sequence")
        #expect(params["order_id"] as? String == "aw")
        #expect(params["segment_ids"] as? [String] == ["c", "d"])
        #expect(params["after_segment_id"] as? String == "a")
        #expect(SegmentEdit.sequence(["c"], after: nil, passId: "z", orders: orders) == .failure(.noOrder))
        #expect(SegmentEdit.sequence([], after: nil, passId: "p", orders: orders) == .failure(.tooFew))
    }
}
