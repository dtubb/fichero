@testable import Fichero
import Foundation
import Testing

/// Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.join-selects-the-joined-segment`. After a
/// Join answers, the selection is the kept segment (the Inspector then shows the joined line); after its undo, the
/// segments that were joined. What breaks without this: the Join clears the selection, so the person cannot see or
/// correct the line they just made.
@MainActor
@Suite(.tags(.paleography))
struct SegmentJoinSelectionTests {
    private func box(_ id: String) -> OCRGeometryBox {
        var box = OCRGeometryBox(
            text: "", bbox: [0, 0, 0, 0], level: "line", confidence: nil, pageIndex: nil, charStart: nil, charEnd: nil,
            provider: nil, source: nil
        )
        box.segmentId = id
        return box
    }

    @Test("after the join answers, the segments that are gone leave the kept id alone selected")
    func joinedSelectsTheKept() {
        #expect(SegmentEdit.selectionAfterJoin(joined: ["l2", "l1", "l3"], live: ["l2", "other"]) == ["l2"])
    }

    @Test("after undo, every joined id is back and is selected, in the order they were picked")
    func undoneSelectsTheRestored() {
        #expect(SegmentEdit.selectionAfterJoin(joined: ["l2", "l1"], live: ["l1", "l2", "x"]) == ["l2", "l1"])
    }

    @Test("a zero-rect, textless box is found by its segment id, so the kept one is selected and not the first")
    func zeroRectBoxesAreToldApartByTheirId() {
        let boxes = [box("l1"), box("l2"), box("l3")]
        let selection = RegionSelection()
        selection.select(1, artifactId: "scope", documentId: "page-1", in: boxes)
        #expect(selection.resolvedIndices(in: boxes) == [1])
        // The store re-reads and the list is rebuilt without l1: the kept box is still the one found.
        let after = [box("l2"), box("l3")]
        #expect(selection.resolvedIndices(in: after) == [0])
    }
}
