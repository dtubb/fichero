@testable import Fichero
import Testing

/// Several unread or unshaped segments share a zero rect and no text. Keyed by shape alone they were one box: a
/// multi-pick found the first every time (only it lit), and a colour looked up by key was the first one's.
@MainActor
struct BoxKeyIdentityTests {
    private func box(id: String?, bbox: [Double] = [0, 0, 0, 0]) -> OCRGeometryBox {
        var box = OCRGeometryBox(
            text: "", bbox: bbox, level: "line", confidence: nil, pageIndex: nil, charStart: nil, charEnd: nil,
            provider: nil, source: nil
        )
        box.segmentId = id
        return box
    }

    @Test("a multi-pick of segments with the same rect and no text selects them all")
    func multiPickKeepsEveryBox() {
        let boxes = [box(id: "a"), box(id: "b"), box(id: "c")]
        let selection = RegionSelection()
        selection.selectAll([0, 1, 2], artifactId: "x", documentId: "d", in: boxes)
        #expect(selection.resolvedIndices(in: boxes) == [0, 1, 2])
    }

    @Test("geometry with no ids still matches by shape, as before")
    func idlessGeometryMatchesByShape() {
        let withIds = [box(id: "a", bbox: [0.1, 0.1, 0.2, 0.2])]
        let without = [box(id: nil, bbox: [0.1, 0.1, 0.2, 0.2])]
        #expect(BoxKey(withIds[0]) == BoxKey(without[0]))
    }

    @Test("two ids that differ are two keys")
    func differentIdsDiffer() {
        #expect(BoxKey(box(id: "a")) != BoxKey(box(id: "b")))
    }
}
