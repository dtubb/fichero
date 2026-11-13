@testable import Fichero
import FicheroAPIClient
import Foundation
import SwiftUI
import Testing

/// Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.split-knife`. A Knife stroke is sent
/// ONCE, as `segment.split` with `cut_path` in the page's fractions (the frame it was drawn in), naming with their
/// versions the lines whose boxes it reaches; the engine decides which it crosses. K held, with no modifier, in Edit
/// Segments, is the Knife for one stroke. What breaks without these: a split per line (an undo per line), a stroke
/// sent in view points, a line edited by somebody else cut anyway, or ⌘K taken by the Knife.
@MainActor
@Suite(.tags(.paleography))
struct KnifeStrokeTests {
    private func line(_ id: String, version: Int?, rect: [Double], baseline: [[Double]]? = nil) -> Segment {
        let anchor = SourceAnchorValue(
            generated: Components.Schemas.SourceAnchorOutput(documentId: "page-1", rect: rect)
        )
        let drawn = baseline ?? [[rect[0], rect[1] + rect[3] * 0.8], [rect[0] + rect[2], rect[1] + rect[3] * 0.8]]
        return Segment(
            id: id, provisional: false, documentId: "page-1", passId: "imported",
            kind: "line", kindRaw: nil, version: version, provenanceKind: .externalImport, anchor: anchor,
            baseline: drawn, text: nil, confidence: nil, language: nil, script: nil, direction: nil,
            sourceArtifactId: nil, boxIndex: 0, pageIndex: nil, metadata: nil
        )
    }

    private func json(_ call: SegmentEdit.Call) throws -> [String: Any] {
        let data = try JSONEncoder().encode(call.params)
        return try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    @Test("one stroke over two lines is one segment.split with the stroke as drawn and both lines' versions")
    func oneCallForTheStroke() throws {
        let stroke: [[Double]] = [[0.5, 0.15], [0.5, 0.4]]
        let call = try SegmentEdit.knife(stroke, over: [
            line("top", version: 3, rect: [0.1, 0.2, 0.8, 0.05]),
            line("bottom", version: 1, rect: [0.1, 0.3, 0.8, 0.05]),
            line("far", version: 2, rect: [0.1, 0.8, 0.8, 0.05])
        ]).get()
        let params = try json(call)
        #expect(call.action == "segment.split")
        #expect(params["cut_path"] as? [[Double]] == stroke)
        #expect(params["expected_versions"] as? [String: Int] == ["top": 3, "bottom": 1])
        #expect(params["segment_id"] == nil)
        #expect(params["parts"] == nil)
    }

    @Test("lines with no baseline or no version are not offered; a stroke that reaches nothing sends nothing")
    func whatIsNotOffered() throws {
        let stroke: [[Double]] = [[0.5, 0.15], [0.5, 0.4]]
        let noBaseline = Segment(
            id: "box", provisional: false, documentId: "page-1", passId: "imported", kind: "line", kindRaw: nil,
            version: 1, provenanceKind: .externalImport,
            anchor: SourceAnchorValue(generated: Components.Schemas.SourceAnchorOutput(documentId: "page-1", rect: [0.1, 0.3, 0.8, 0.05])),
            baseline: nil, text: nil, confidence: nil, language: nil, script: nil, direction: nil,
            sourceArtifactId: nil, boxIndex: 0, pageIndex: nil, metadata: nil
        )
        let params = try json(SegmentEdit.knife(stroke, over: [
            line("top", version: 3, rect: [0.1, 0.2, 0.8, 0.05]), noBaseline,
            line("unsaved", version: nil, rect: [0.1, 0.25, 0.8, 0.04])
        ]).get())
        #expect(params["expected_versions"] as? [String: Int] == ["top": 3])
        #expect(SegmentEdit.knife(stroke, over: [line("far", version: 1, rect: [0.1, 0.8, 0.8, 0.05])]) == .failure(.tooFew))
        #expect(SegmentEdit.knife([[0.5, 0.2]], over: [line("top", version: 1, rect: [0.1, 0.2, 0.8, 0.05])]) == .failure(.tooFew))
        #expect(SegmentEdit.knife(stroke, over: [line("unsaved", version: nil, rect: [0.1, 0.2, 0.8, 0.05])])
            == .failure(.versionUnknown))
    }

    @Test("a slow drag is thinned before it is sent, and still ends where it was let go")
    func thinned() {
        let drag = (0...100).map { [0.5, 0.2 + Double($0) * 0.0001] }
        let sent = KnifeStroke.thinned(drag)
        #expect(sent.count < 10)
        #expect(sent.first == drag.first)
        #expect(sent.last == drag.last)
    }

    @Test("K with no modifier in Edit Segments holds the Knife; letting go puts it back; ⌘K and K outside are not the Knife's")
    func theKey() {
        #expect(KnifeStroke.held(pressed: true, modifiers: [], isEditing: true, wasHeld: false) == true)
        #expect(KnifeStroke.held(pressed: false, modifiers: [], isEditing: true, wasHeld: true) == false)
        #expect(KnifeStroke.held(pressed: true, modifiers: .command, isEditing: true, wasHeld: false) == nil)
        #expect(KnifeStroke.held(pressed: true, modifiers: [], isEditing: false, wasHeld: false) == nil)
        #expect(KnifeStroke.held(pressed: false, modifiers: [], isEditing: true, wasHeld: false) == nil)
    }

    @Test("the Knife chosen from the tool row stays until another tool is chosen")
    func choosingAnotherToolPutsTheKnifeDown() {
        let window = WindowState(libraryId: UUID())
        window.activeMarkupTool = .select
        window.knifeArmed = true
        window.activeMarkupTool = .select
        #expect(window.knifeArmed, "choosing the same tool again is not another tool")
        window.activeMarkupTool = .drawRegion
        #expect(!window.knifeArmed)
    }

    @Test("Split Line at Point is the Knife's call: a short stroke through the point's foot, across the baseline")
    func splitAtAPoint() throws {
        let call = try SegmentEdit.splitAtPoint(
            line("l1", version: 4, rect: [0.1, 0.2, 0.8, 0.05], baseline: [[0.1, 0.24], [0.9, 0.24]]), at: [0.4, 0.21]
        ).get()
        let params = try json(call)
        #expect(call.action == "segment.split")
        #expect(params["expected_versions"] as? [String: Int] == ["l1": 4])
        let stroke = try #require(params["cut_path"] as? [[Double]])
        #expect(stroke.count == 2)
        #expect(stroke.allSatisfy { abs($0[0] - 0.4) < 1e-9 }, "at right angles to a level baseline, through x = 0.4")
        #expect(stroke.map { $0[1] }.min()! < 0.24 && stroke.map { $0[1] }.max()! > 0.24, "it crosses the baseline")
        #expect(SegmentEdit.splitAtPoint(
            line("l1", version: 4, rect: [0.1, 0.2, 0.8, 0.05], baseline: [[0.1, 0.24]]), at: [0.4, 0.21]
        ) == .failure(.noBaseline))
        #expect(!SegmentMenuContent.canSplitAtPoint(selected: 2, hasBaselines: true))
        #expect(SegmentMenuContent.canSplitAtPoint(selected: 1, hasBaselines: true))
    }

    @Test("the Knife says how many lines it left alone, and says nothing when it cut every line it reached")
    func notice() {
        #expect(SegmentEdit.knifeNotice(cut: 2, leftAlone: 0) == nil)
        #expect(SegmentEdit.knifeNotice(cut: 1, leftAlone: 1) == "Cut 1 line; 1 line the stroke did not cross was left alone")
        #expect(SegmentEdit.knifeNotice(cut: 0, leftAlone: 3)?.contains("3 lines") == true)
        #expect(ActionInvokeResult.listCounts(["splits": [1, 2], "left_alone": [Int](), "id": "x"] as [String: (any Sendable)?])
            == ["splits": 2, "left_alone": 0])
    }
}
