@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// Tab and Shift-Tab in the nested Order list (#6476, `source.editor.order-list-indents-with-tab`).
struct OrderListIndentTests {
    private func segment(_ id: String, kind: String, parent: String? = nil) -> Segment {
        Segment(
            id: id, provisional: false, documentId: "p1", passId: "p", kind: kind, kindRaw: nil,
            parentSegmentId: parent, provenanceKind: .externalImport,
            anchor: SourceAnchorValue(generated: Components.Schemas.SourceAnchorOutput(documentId: "p1")),
            baseline: nil, text: nil, confidence: nil, sourceArtifactId: nil, boxIndex: nil, pageIndex: nil, metadata: nil
        )
    }

    /// Region 1 holding two lines, then a loose line, then Region 2 holding one.
    private var page: [Segment] {
        [segment("r1", kind: "region"), segment("l1", kind: "line", parent: "r1"), segment("l2", kind: "line", parent: "r1"),
         segment("loose", kind: "line"), segment("r2", kind: "region"), segment("l3", kind: "line", parent: "r2")]
    }

    private var outline: [SegmentsPane.OutlineRow] { SegmentsPane.outline(page, top: ["r1", "loose", "r2"]) }

    @Test("Tab puts a loose line into the region above it; a line whose neighbour above is a line stays")
    func tabIndents() {
        #expect(OrderDrop.indentTarget(["loose"], outline: outline, in: page) == "r1")
        #expect(OrderDrop.indentTarget(["l2"], outline: outline, in: page) == nil, "a line cannot hold a line")
        #expect(OrderDrop.indentTarget(["r1"], outline: outline, in: page) == nil, "nothing above the first row")
        #expect(OrderDrop.indentTarget(["r2"], outline: outline, in: page) == nil, "a region never goes into a line")
    }

    @Test("Shift-Tab takes lines out of their region to the page; rows at the top or under two parents stay")
    func shiftTabOutdents() {
        #expect(OrderDrop.outdentTarget(["l1", "l2"], in: page) == .init(parent: nil))
        #expect(OrderDrop.outdentTarget(["loose"], in: page) == nil)
        #expect(OrderDrop.outdentTarget(["l1", "l3"], in: page) == nil)
    }

    @Test("the selection is taken in the order the outline shows it")
    func outlineOrder() {
        #expect(OrderDrop.inOutlineOrder(["l3", "loose", "l1"], outline: outline) == ["l1", "loose", "l3"])
    }
}
