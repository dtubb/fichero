@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.regenerate-polygon-from-baseline` and
/// `segment-editor.edge.no-baseline`. Redraw Outline from Baseline sends every selected line in one
/// `segment.regenerate_outline`, with the versions the app read, so the whole selection is one action and one undo;
/// a line with no baseline is refused before anything is sent, and the menu says why. What breaks without these:
/// a redraw per line (many undos), or a redraw of a box with no baseline that the engine refuses with no word.
@MainActor
@Suite(.tags(.paleography))
struct RedrawOutlineTests {
    private func line(_ id: String, version: Int?, baseline: [[Double]]?) -> Segment {
        let anchor = SourceAnchorValue(
            generated: Components.Schemas.SourceAnchorOutput(documentId: "page-1", rect: [0, 0.2, 1, 0.05])
        )
        return Segment(
            id: id, provisional: false, documentId: "page-1", passId: "imported",
            kind: "line", kindRaw: nil, version: version, provenanceKind: .externalImport, anchor: anchor,
            baseline: baseline, text: nil, confidence: nil, language: nil, script: nil, direction: nil,
            sourceArtifactId: nil, boxIndex: 0, pageIndex: nil, metadata: nil
        )
    }

    private let flat: [[Double]] = [[0.1, 0.24], [0.9, 0.24]]

    @Test("a selection of lines is one segment.regenerate_outline, in the order picked, with the versions read")
    func oneCallForTheSelection() throws {
        let call = try SegmentEdit.redrawOutline([
            line("l2", version: 3, baseline: flat), line("l1", version: 1, baseline: flat)
        ]).get()
        let data = try JSONEncoder().encode(call.params)
        let params = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(call.action == "segment.regenerate_outline")
        #expect(params["segment_ids"] as? [String] == ["l2", "l1"])
        #expect(params["expected_versions"] as? [String: Int] == ["l2": 3, "l1": 1])
        #expect(params["fixed_height"] == nil)
    }

    @Test("a line with no baseline, or one point of one, is refused before anything is sent")
    func noBaselineIsRefused() {
        #expect(SegmentEdit.redrawOutline([line("l1", version: 1, baseline: nil)]) == .failure(.noBaseline))
        #expect(SegmentEdit.redrawOutline([line("l1", version: 1, baseline: [[0.1, 0.2]])]) == .failure(.noBaseline))
        #expect(SegmentEdit.redrawOutline([
            line("l1", version: 1, baseline: flat), line("l2", version: 1, baseline: nil)
        ]) == .failure(.noBaseline))
        #expect(SegmentEdit.redrawOutline([]) == .failure(.tooFew))
        #expect(SegmentEdit.redrawOutline([line("l1", version: nil, baseline: flat)]) == .failure(.versionUnknown))
    }

    @Test("the menu item acts on lines with baselines, and says why when it cannot")
    func menuSaysWhy() {
        #expect(SegmentMenuContent.redrawReason(selected: 2, hasBaselines: true) == nil)
        #expect(SegmentMenuContent.redrawReason(selected: 0, hasBaselines: false) != nil)
        #expect(SegmentMenuContent.redrawReason(selected: 1, hasBaselines: false)?.contains("baseline") == true)
    }

    @Test("Add Baseline sends only the lines that have none, as one segment.add_baseline")
    func addBaseline() throws {
        let call = try SegmentEdit.addBaseline([
            line("boxed", version: 2, baseline: nil), line("drawn", version: 1, baseline: flat)
        ]).get()
        let data = try JSONEncoder().encode(call.params)
        let params = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(call.action == "segment.add_baseline")
        #expect(params["segment_ids"] as? [String] == ["boxed"])
        #expect(params["expected_versions"] as? [String: Int] == ["boxed": 2])
        #expect(SegmentEdit.addBaseline([line("drawn", version: 1, baseline: flat)]) == .failure(.tooFew))
        #expect(SegmentMenuContent.redrawReason(selected: 1, hasBaselines: false)?.contains("Add Baseline") == true)
    }
}
