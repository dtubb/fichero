@testable import Fichero
import Foundation
import Testing

/// Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.list-drag-reorder`. Rows dropped between rows
/// of the segment list land just before the row dropped on, several at once in their list order, as ONE
/// `reading_order.move` (one undo by its `reading_order.restore_places`). What breaks without these: a move per row (one
/// ⌘Z each), the dragged rows landing in drag order instead of list order, or a drop where they already are written to
/// the audit trail.
@MainActor
struct OrderListDropReorderTests {
    private let level: [ReadingOrderMove.Entry] = ["a", "b", "c", "d", "e"].map {
        .init(entryId: "e-\($0)", segmentId: $0, version: 1)
    }

    private func params(_ call: SegmentEdit.Call) throws -> [String: Any] {
        let data = try JSONEncoder().encode(call.params)
        return try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    @Test("a drop between rows is one reading_order.move after the row above the drop")
    func dropBetweenRowsReorders() throws {
        let call = try ReadingOrderMove.move(orderId: "o1", entries: level, moving: ["e"], before: "c").get()
        let sent = try params(call)
        #expect(call.action == "reading_order.move")
        #expect(sent["order_id"] as? String == "o1")
        #expect(sent["segment_ids"] as? [String] == ["e"])
        #expect(sent["after_segment_id"] as? String == "b")
        #expect(sent["parent_segment_id"] == nil)
    }

    @Test("several dragged rows keep their list order, whatever order the drag named them in")
    func multiRowKeepsRelativeOrder() throws {
        let call = try ReadingOrderMove.move(orderId: "o1", entries: level, moving: ["e", "a"], before: "d").get()
        let sent = try params(call)
        #expect(sent["segment_ids"] as? [String] == ["a", "e"])
        #expect(sent["after_segment_id"] as? String == "c")
    }

    @Test("a drop before the first row sends no after; under a region it names the region as parent")
    func firstPlaceAndParent() throws {
        let call = try ReadingOrderMove.move(
            orderId: "o1", entries: level, moving: ["c"], before: "a", parentSegmentId: "region-1"
        ).get()
        let sent = try params(call)
        #expect(sent["after_segment_id"] == nil)
        #expect(sent["parent_segment_id"] as? String == "region-1")
    }

    @Test("a drop where the rows already are, on a dragged row, or with a row from another level sends nothing")
    func refusals() {
        #expect(ReadingOrderMove.move(orderId: "o1", entries: level, moving: ["b"], before: "c") == .failure(.alreadyThere))
        #expect(ReadingOrderMove.move(orderId: "o1", entries: level, moving: ["b", "c"], before: "c") == .failure(.alreadyThere))
        #expect(ReadingOrderMove.move(orderId: "o1", entries: level, moving: ["x"], before: "c") == .failure(.notInThisOrder))
        #expect(ReadingOrderMove.move(orderId: "o1", entries: level, moving: ["a"], before: "x") == .failure(.targetOutOfRange))
    }
}
