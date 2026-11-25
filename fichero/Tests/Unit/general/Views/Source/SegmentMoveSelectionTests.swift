@testable import Fichero
import Foundation
import Testing

/// Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.move-keeps-selection`. After a move
/// answers (and after its undo or redo) the moved segments are the selection, in the Preview, the Inspector and the
/// Segments list, which all read the one selection. What breaks without this: the drag ends and nothing is selected.
@MainActor
@Suite(.tags(.paleography))
struct SegmentMoveSelectionTests {
    private func box(_ id: String, _ rect: [Double]) -> OCRGeometryBox {
        var box = OCRGeometryBox(
            text: "", bbox: rect, level: "line", confidence: nil, pageIndex: nil, charStart: nil, charEnd: nil,
            provider: nil, source: nil
        )
        box.segmentId = id
        return box
    }

    @Test("the moved ids stay selected, in the order they were picked, and an id the store lost is left out")
    func movedStaySelected() {
        #expect(SegmentEdit.selectionAfterMove(moved: ["b", "a"], live: ["a", "b", "x"]) == ["b", "a"])
        #expect(SegmentEdit.selectionAfterMove(moved: ["b", "a"], live: ["a"]) == ["a"])
    }

    @Test("a selection made by identity loses a box whose rect moved; writing it again by segment id finds it")
    func selectionByIdSurvivesTheMove() {
        let before = [box("l1", [0.1, 0.1, 0.3, 0.05]), box("l2", [0.1, 0.2, 0.3, 0.05])]
        let selection = RegionSelection()
        selection.select(0, artifactId: "scope", documentId: "p", in: before)
        let after = [box("l1", [0.2, 0.15, 0.3, 0.05]), box("l2", [0.1, 0.2, 0.3, 0.05])]
        #expect(selection.resolvedIndices(in: after).isEmpty, "this is the bug: the moved box is no longer found")
        selection.selectAll([0], artifactId: "scope", documentId: "p", in: after)
        #expect(selection.resolvedIndices(in: after) == [0])
    }

    @Test("both move paths reselect the moved segments after the re-read")
    func movePathsReselect() throws {
        let source = try String(
            contentsOf: AppSource.root().appendingPathComponent(
                "Views/Preview/ImageViewer/Regions/Zoomable/ZoomableImagePreviewMac+SegmentEdits.swift"
            ), encoding: .utf8
        )
        #expect(source.contains("afterReread: reselectAfterMove(segments.map(\\.id), documentId: documentId)"))
        #expect(source.contains("afterReread: reselectAfterMove([segment.id], documentId: documentId)"))
    }
}
